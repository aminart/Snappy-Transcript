from __future__ import annotations
import logging, queue, threading, time, wave
from dataclasses import dataclass
from pathlib import Path
from audio.base import AudioSource
from models.transcript import TranscriptSegment
from transcription.base import TranscriptionProvider
from services.cache_writer import TranscriptCache
from utils.paths import app_data_dir

log = logging.getLogger(__name__)

@dataclass
class SessionStats:
    chunks_processed:int=0; last_latency:float=0.0; last_chunk_duration:float=0.0
    realtime_ratio:float=0.0; average_realtime_ratio:float=0.0; last_error:str=''
    dropped_audio_blocks:int=0; overlap_seconds:float=0.0; duplicate_words_removed:int=0

class LiveSession:
    """Long-session friendly capture: audio is spooled to WAV instead of retained in RAM."""
    def __init__(self, source:AudioSource, provider:TranscriptionProvider, chunk_seconds:float,
                 language:str, save_audio:bool=True, overlap_seconds:float=.75, session_id:str='session'):
        self.source,self.provider=source,provider; self.sample_rate=getattr(source,'sample_rate',16000)
        self.chunk_seconds=float(chunk_seconds); self.overlap_seconds=max(0.,min(float(overlap_seconds),self.chunk_seconds-.25))
        self.chunk_bytes=int(self.chunk_seconds*self.sample_rate*2); self.step_bytes=max(2,int((self.chunk_seconds-self.overlap_seconds)*self.sample_rate*2))
        self.language=language; self.save_audio=save_audio; self.session_id=session_id; self.stats=SessionStats(overlap_seconds=self.overlap_seconds)
        self._segments=[]; self._lock=threading.Lock(); self._stop=threading.Event(); self._pause=threading.Event(); self._stopped_while_paused=False; self._capture_done=threading.Event()
        self._tasks=queue.Queue(maxsize=100); self._capture_thread=None; self._stt_thread=None
        self._pending=bytearray(); self._window_start_bytes=0; self._status='STOPPED'; self._ratio_sum=0.; self._captured_bytes=0
        self.cache=TranscriptCache(session_id); self.cache.write([])
        root=app_data_dir()/'sessions'/session_id
        root.mkdir(parents=True,exist_ok=True); self.session_dir=root; self.wav_path=root/f'recording_{session_id}.wav'
        self._wav=None

    @property
    def status(self):
        with self._lock:status=self._status
        # stop() et la fin du thread STT se disputent le statut : une session finalisée est toujours « STOPPED ».
        return 'STOPPED' if status!='ERROR' and self.is_finalized else status
    @property
    def duration(self):
        with self._lock:return self._captured_bytes/(2*self.sample_rate)
    @property
    def queue_size(self):return self._tasks.qsize()
    def segments(self):
        with self._lock:return list(self._segments)
    def _set_status(self,s):
        with self._lock:self._status=s
    def start(self):
        self._wav=wave.open(str(self.wav_path),'wb'); self._wav.setnchannels(1); self._wav.setsampwidth(2); self._wav.setframerate(self.sample_rate)
        try:self.source.start()
        except Exception:
            # Périphérique occupé ou absent : ne pas laisser un WAV ouvert et vide derrière nous.
            self._wav.close(); self._wav=None
            raise
        self._set_status('LISTENING')
        self._capture_thread=threading.Thread(target=self._capture,name='audio-capture',daemon=True); self._stt_thread=threading.Thread(target=self._transcribe,name='stt-worker',daemon=True)
        self._capture_thread.start(); self._stt_thread.start()
    def _store(self,block):
        if not block:return
        self._wav.writeframesraw(block)
        with self._lock:self._captured_bytes+=len(block)
        self._pending.extend(block)
    def _enqueue(self,offset,pcm):
        if not pcm:return
        try:self._tasks.put((offset,pcm),timeout=1)
        except queue.Full:self.stats.last_error='File STT saturée : WAV conservé, un chunk de transcription a été ignoré.'
    def _emit_full_windows(self):
        while len(self._pending)>=self.chunk_bytes:
            self._enqueue(self._window_start_bytes,bytes(self._pending[:self.chunk_bytes])); del self._pending[:self.step_bytes]; self._window_start_bytes+=self.step_bytes
    def _capture(self):
        try:
            while not self._stop.is_set():
                block=self.source.read_chunk(timeout=.1)
                if not block:continue
                if self._pause.is_set():
                    continue
                self._store(block); self._emit_full_windows()
        except Exception as exc:
            log.exception('Audio capture failed'); self.stats.last_error=f'Capture audio : {type(exc).__name__}: {exc}'; self._set_status('ERROR')
        finally:
            # Quoi qu'il arrive ci-dessous, _capture_done et le marqueur de fin doivent partir : sinon STOP
            # échoue et le thread STT ne se termine jamais.
            try:
                try:self.source.stop()
                except Exception as exc:self.stats.last_error=f'Fermeture micro : {exc}'
                if not self._stopped_while_paused:
                    try:
                        while True:
                            block=self.source.read_chunk(timeout=0)
                            if not block:break
                            self._store(block)
                    except Exception as exc:
                        # Une source en échec (ex. boucle système) re-lève son erreur à la lecture.
                        log.warning('Drain audio interrompu : %s',exc)
                self._emit_full_windows()
                if self._pending and len(self._pending)>int(self.overlap_seconds*self.sample_rate*2):self._enqueue(self._window_start_bytes,bytes(self._pending))
                try:
                    if self._wav:self._wav.close(); self._wav=None
                except Exception as exc:log.warning('WAV close failed: %s',exc)
            finally:
                self._capture_done.set(); self._tasks.put(None)
    @staticmethod
    def _word_overlap(previous,current,max_words=12):
        a=previous.strip().split(); b=current.strip().split(); limit=min(max_words,len(a),len(b))
        for n in range(limit,0,-1):
            if [w.strip('.,;:!?…').casefold() for w in a[-n:]]==[w.strip('.,;:!?…').casefold() for w in b[:n]]:return n
        return 0
    def _merge_result(self,result):
        with self._lock:
            for seg in result:
                text=seg.text.strip()
                if not text:continue
                start=seg.start
                if self._segments:
                    prev=self._segments[-1]
                    # Un doublon ne peut venir que du recouvrement : le nouveau segment commence alors avant la fin
                    # du précédent. Sans cette garde, « Merci. » dit à 10 minutes d'écart perdait son premier mot.
                    n=self._word_overlap(prev.text,text) if seg.start<=prev.end+.5 else 0
                    if n:
                        text=' '.join(text.split()[n:]).strip(); seg_words=seg.words[n:] if len(seg.words)>=n else seg.words; self.stats.duplicate_words_removed+=n
                        if seg_words:start=seg_words[0].start
                    else:seg_words=seg.words
                    if not text:continue
                else:seg_words=seg.words
                self._segments.append(TranscriptSegment(start,seg.end,text,seg.speaker,tuple(seg_words)))
            try:self.cache.write(list(self._segments))
            except Exception as exc:log.warning('Transcript cache write failed: %s',exc)
    def _transcribe(self):
        while True:
            task=self._tasks.get()
            if task is None:self._tasks.task_done();break
            offset,pcm=task; dur=len(pcm)/(2*self.sample_rate); self.stats.last_chunk_duration=dur
            if self.status not in ('ERROR','PAUSED'):self._set_status('TRANSCRIBING')
            start=time.monotonic()
            try:
                self._merge_result(self.provider.transcribe(pcm,self.sample_rate,offset/(2*self.sample_rate),self.language)); self.stats.chunks_processed+=1
            except Exception as exc:
                log.exception('Transcription failed'); self.stats.last_error=f'Transcription : {type(exc).__name__}: {exc}'; self._set_status('ERROR')
            finally:
                self.stats.last_latency=time.monotonic()-start; ratio=self.stats.last_latency/dur if dur else 0.; self.stats.realtime_ratio=ratio
                if dur:self._ratio_sum+=ratio; self.stats.average_realtime_ratio=self._ratio_sum/max(1,self.stats.chunks_processed)
                # Une pause demandée pendant ce chunk ne doit pas être écrasée par « LISTENING ».
                if not self._stop.is_set() and self.status!='ERROR':self._set_status('PAUSED' if self._pause.is_set() else 'LISTENING')
                self._tasks.task_done()
        if self.status!='ERROR':self._set_status('STOPPED')
    @property
    def is_paused(self): return self._pause.is_set()
    def pause(self):
        if self._stop.is_set(): return
        self._pause.set(); self._set_status('PAUSED')
    def resume(self):
        if self._stop.is_set(): return
        self._pause.clear(); self._set_status('LISTENING')
    def stop(self):
        self._stopped_while_paused=self._pause.is_set()
        self._pause.clear(); self._stop.set()
        if self._capture_thread:self._capture_thread.join(timeout=10)
        if not self._capture_done.is_set():raise RuntimeError('Le thread audio ne s’est pas arrêté dans le délai imparti.')
        if self.status!='ERROR':self._set_status('TRANSCRIBING')
    @property
    def is_finalized(self):return self._capture_done.is_set() and self._stt_thread is not None and not self._stt_thread.is_alive()
    def replace_segments(self,segments):
        with self._lock:
            self._segments=list(segments)
            try:self.cache.write(list(self._segments))
            except Exception as exc:log.warning('Transcript cache write failed: %s',exc)

from __future__ import annotations
import ctypes
import logging
import queue
import sys
import threading
from contextlib import contextmanager

import numpy as np
from .base import AudioSource

log = logging.getLogger(__name__)

# Streamlit executes app code and workers on threads that are not guaranteed to
# have COM initialized. SoundCard's Windows MediaFoundation backend needs COM on
# every thread that touches it. We do this locally: no pywin32/admin dependency.
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106: COM already initialized differently

@contextmanager
def _com_initialized():
    if sys.platform != 'win32':
        yield
        return
    ole32 = ctypes.windll.ole32
    hr = int(ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED))
    initialized_here = hr in (0, 1)  # S_OK / S_FALSE
    if hr < 0 and hr != _RPC_E_CHANGED_MODE:
        raise RuntimeError(f'Initialisation COM Windows impossible (HRESULT 0x{hr & 0xFFFFFFFF:08X}).')
    try:
        yield
    finally:
        if initialized_here:
            ole32.CoUninitialize()


def _soundcard():
    try:
        import soundcard as sc
        return sc
    except ImportError as e:
        raise RuntimeError('Capture audio système : installe soundcard (requirements.txt).') from e


class SystemAudioSource(AudioSource):
    """Windows WASAPI loopback via SoundCard. No virtual driver/admin rights required."""
    def __init__(self, speaker_name: str | None=None, sample_rate:int=16000, channels:int=1, block_ms:int=100):
        self.sample_rate=sample_rate; self.channels=channels; self.blocksize=int(sample_rate*block_ms/1000)
        self.speaker_name=speaker_name; self._q=queue.Queue(maxsize=200); self._stop=threading.Event(); self._thread=None

    def start(self):
        # Do not create/retain MediaFoundation COM objects on the Streamlit
        # thread. Resolve the speaker and loopback microphone in the capture
        # worker that will actually use them.
        self._stop.clear()

        def run():
            try:
                with _com_initialized():
                    sc = _soundcard()
                    speakers = sc.all_speakers()
                    sp = next((x for x in speakers if self.speaker_name and x.name == self.speaker_name), None) or sc.default_speaker()
                    if sp is None:
                        raise RuntimeError('Aucune sortie audio Windows détectée.')
                    mic = sc.get_microphone(id=sp.id, include_loopback=True)
                    with mic.recorder(samplerate=self.sample_rate, channels=1, blocksize=self.blocksize) as rec:
                        while not self._stop.is_set():
                            a=rec.record(numframes=self.blocksize)
                            pcm=np.clip(a[:,0] if a.ndim>1 else a,-1,1)
                            b=(pcm*32767).astype(np.int16).tobytes()
                            try:self._q.put_nowait(b)
                            except queue.Full:
                                try:self._q.get_nowait(); self._q.put_nowait(b)
                                except queue.Empty:pass
            except Exception as e:
                log.exception('WASAPI loopback failed')
                try:self._q.put_nowait(e)
                except queue.Full:pass

        self._thread=threading.Thread(target=run,name='wasapi-loopback',daemon=True); self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=2); self._thread=None

    def read_chunk(self,timeout=.2):
        try:x=self._q.get(timeout=timeout)
        except queue.Empty:return None
        if isinstance(x,Exception):raise x
        return x


def list_output_devices():
    """Enumerate Windows outputs without letting a COM failure crash Streamlit."""
    try:
        with _com_initialized():
            sc = _soundcard()
            return [{'name':s.name,'id':str(s.id)} for s in sc.all_speakers()]
    except Exception as exc:
        log.warning('System audio enumeration unavailable: %s: %s', type(exc).__name__, exc)
        return []


class MixedAudioSource(AudioSource):
    """Mix microphone + loopback into one mono PCM16 stream."""
    def __init__(self,microphone:AudioSource,system:AudioSource,sample_rate=16000,block_ms=100,mic_gain=1.0,system_gain=1.0):
        self.microphone=microphone; self.system=system; self.sample_rate=sample_rate; self.blocksize=int(sample_rate*block_ms/1000)
        self.mic_gain=float(mic_gain); self.system_gain=float(system_gain); self._q=queue.Queue(maxsize=200); self._stop=threading.Event(); self._threads=[]
        self._mq=queue.Queue(maxsize=20); self._sq=queue.Queue(maxsize=20)
    @staticmethod
    def _put(q,b):
        try:q.put_nowait(b)
        except queue.Full:
            try:q.get_nowait();q.put_nowait(b)
            except queue.Empty:pass
    def start(self):
        self._stop.clear(); self.microphone.start(); self.system.start()
        def pump(src,q):
            while not self._stop.is_set():
                try:
                    b=src.read_chunk(.1)
                    if b:self._put(q,b)
                except Exception as exc:
                    self._put(self._q, exc)
                    self._stop.set()
                    break
        for src,q,name in [(self.microphone,self._mq,'mix-mic'),(self.system,self._sq,'mix-system')]:
            t=threading.Thread(target=pump,args=(src,q),name=name,daemon=True);t.start();self._threads.append(t)
        def mix():
            silence=np.zeros(self.blocksize,dtype=np.int16)
            while not self._stop.is_set():
                try:mb=self._mq.get(timeout=.12)
                except queue.Empty:mb=silence.tobytes()
                try:sb=self._sq.get(timeout=.03)
                except queue.Empty:sb=silence.tobytes()
                m=np.frombuffer(mb,dtype=np.int16); s=np.frombuffer(sb,dtype=np.int16); n=min(len(m),len(s))
                if not n:continue
                y=np.clip(m[:n].astype(np.float32)*self.mic_gain+s[:n].astype(np.float32)*self.system_gain,-32768,32767).astype(np.int16)
                self._put(self._q,y.tobytes())
        t=threading.Thread(target=mix,name='audio-mixer',daemon=True);t.start();self._threads.append(t)
    def stop(self):
        self._stop.set(); self.microphone.stop(); self.system.stop()
        for t in self._threads:t.join(timeout=1)
        self._threads=[]
    def read_chunk(self,timeout=.2):
        try:x=self._q.get(timeout=timeout)
        except queue.Empty:return None
        if isinstance(x,Exception):raise x
        return x

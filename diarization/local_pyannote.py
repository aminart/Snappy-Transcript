from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import wave, numpy as np, time
from models.transcript import TranscriptSegment, TranscriptWord

def validate_diarization_model(path):
    p=Path((path or '').strip().strip('"')).expanduser()
    if not path:return False,'Aucun dossier de pipeline renseigné.'
    if not p.is_dir():return False,f'Dossier introuvable : {p}'
    if not (p/'config.yaml').is_file():return False,'config.yaml absent : sélectionne le dossier racine du pipeline pyannote local.'
    req=(p/'embedding'/'pytorch_model.bin',p/'segmentation'/'pytorch_model.bin',p/'plda'/'plda.npz',p/'plda'/'xvec_transform.npz')
    missing=[str(x.relative_to(p)) for x in req if not x.is_file()]
    return (False,'Pipeline incomplet : '+', '.join(missing)) if missing else (True,str(p))
def _turns(a):return [(float(t.start),float(t.end),str(l)) for t,_,l in a.itertracks(yield_label=True)]
def _best(turns,start,end):
    label=None; best=0.
    for a,b,l in turns:
        ov=max(0.,min(end,b)-max(start,a))
        if ov>best:best,label=ov,l
    if label is None and turns:
        mid=(start+end)/2; label=min(turns,key=lambda t:min(abs(mid-t[0]),abs(mid-t[1])))[2]
    return label
def _merge(segments,turns):
    out=[]
    for seg in segments:
        if not seg.words:out.append(replace(seg,speaker=_best(turns,seg.start,seg.end)));continue
        groups=[]
        for w in seg.words:
            sp=_best(turns,float(w.start),max(float(w.end),float(w.start)+.03))
            if groups and groups[-1][0]==sp:groups[-1][1].append(w)
            else:groups.append((sp,[w]))
        for sp,words in groups:
            text=' '.join(w.text.strip() for w in words if w.text.strip()).strip()
            if text:out.append(TranscriptSegment(float(words[0].start),float(words[-1].end),text,sp,tuple(words)))
    return out
def _pipeline(model_path):
    ok,detail=validate_diarization_model(model_path)
    if not ok:raise ValueError(detail)
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:raise RuntimeError('Diarisation non installée. Installe requirements-diarization.txt') from exc
    return Pipeline.from_pretrained(detail)
def diarize_waveform(waveform,sample_rate,segments,model_path,min_speakers=None,max_speakers=None,progress_callback=None):
    import torch
    p=_pipeline(model_path); tensor=torch.from_numpy(waveform.astype(np.float32,copy=False)).unsqueeze(0)
    kw={}
    if min_speakers:kw['min_speakers']=int(min_speakers)
    if max_speakers:kw['max_speakers']=int(max_speakers)
    class Hook:
        def __init__(self): self.started=time.monotonic(); self.last=0.0
        def __call__(self, step_name, step_artifact=None, file=None, total=None, completed=None, **kwargs):
            # pyannote passes completed/total for iterable pipeline stages.
            if not progress_callback:return
            try:
                c=float(completed or 0); t=float(total or 0); frac=(c/t) if t>0 else None
                now=time.monotonic(); elapsed=now-self.started
                eta=(elapsed/frac-elapsed) if frac and frac>0 else None
                # Throttle UI callbacks slightly; always pass phase changes/final-ish updates.
                if now-self.last>.20 or (frac is not None and frac>=.999):
                    self.last=now; progress_callback(str(step_name),frac,elapsed,eta)
            except Exception: pass
    hook=Hook() if progress_callback else None
    if progress_callback:progress_callback('chargement / préparation',0.0,0.0,None)
    output=p({'waveform':tensor,'sample_rate':int(sample_rate)},hook=hook,**kw) if hook else p({'waveform':tensor,'sample_rate':int(sample_rate)},**kw)
    if progress_callback:progress_callback('fusion transcription / locuteurs',1.0,time.monotonic()-hook.started,0.0)
    ann=getattr(output,'exclusive_speaker_diarization',None) or getattr(output,'speaker_diarization',output)
    return _merge(segments,_turns(ann))
def diarize_wav_file(wav_path,segments,model_path,min_speakers=None,max_speakers=None,progress_callback=None):
    """Offline/post-hoc diarization from a PCM16 mono WAV. No browser/base64 and no FFmpeg."""
    with wave.open(str(wav_path),'rb') as f:
        sr=f.getframerate(); ch=f.getnchannels(); sw=f.getsampwidth(); pcm=f.readframes(f.getnframes())
    if ch!=1 or sw!=2:raise ValueError(f'WAV attendu : mono PCM16. Reçu : {ch} canal(aux), {sw*8} bits.')
    audio=np.frombuffer(pcm,dtype=np.int16).astype(np.float32)/32768.0
    return diarize_waveform(audio,sr,segments,model_path,min_speakers,max_speakers,progress_callback)

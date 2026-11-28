from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import wave, numpy as np, time
from .models import TranscriptSegment, TranscriptWord
import warnings
# pyannote prévient que torchcodec (décodage de fichiers audio) manque : Snappy lui donne l'audio déjà en mémoire
# ({'waveform', 'sample_rate'}), torchcodec ne sert donc jamais. On n'affiche pas cet avertissement trompeur.
warnings.filterwarnings('ignore', message=r'.*torchcodec is not installed correctly.*')

def validate_diarization_model(path):
    p=Path((path or '').strip().strip('"')).expanduser()
    if not path:return False,'Aucun dossier de pipeline renseigné.'
    if not p.is_dir():return False,f'Dossier introuvable : {p}'
    if not (p/'config.yaml').is_file():return False,'config.yaml absent : sélectionne le dossier racine du pipeline pyannote local.'
    req=(p/'embedding'/'pytorch_model.bin',p/'segmentation'/'pytorch_model.bin',p/'plda'/'plda.npz',p/'plda'/'xvec_transform.npz')
    missing=[str(x.relative_to(p)) for x in req if not x.is_file()]
    if missing:return False,'Pipeline incomplet : '+', '.join(missing)
    classe=_classe_du_pipeline(p/'config.yaml')
    if not classe.startswith('pyannote.audio.pipelines.'):
        # config.yaml désigne la classe que pyannote instancie : un dossier piégé pourrait y mettre n'importe quel code
        return False,f"config.yaml refusé : la classe « {classe or '?'} » n'est pas un pipeline pyannote."
    return True,str(p)
def _classe_du_pipeline(config):
    """Valeur de pipeline › name dans config.yaml (lecture sûre, sans rien exécuter)."""
    try:
        import yaml
        d=yaml.safe_load(config.read_text(encoding='utf-8')) or {}
        return str(((d.get('pipeline') or {}).get('name')) or '').strip()
    except ImportError:
        import re
        m=re.search(r'^pipeline:\s*\n(?:[ \t]+.*\n)*?[ \t]+name:\s*["\']?([\w.]+)',config.read_text(encoding='utf-8'),re.M)
        return m.group(1) if m else ''
    except Exception:
        return ''
def _absente(exc):
    """Message quand pyannote ou PyTorch ne se charge pas : on donne la vraie cause (module manquant, DLL bloquée…)."""
    import sys
    cause=f'{type(exc).__name__} : {exc}'
    if getattr(sys,'frozen',False):
        return ("L'identification des intervenants ne se charge pas sur ce poste (" + cause + "). "
                "Lancez « SnappyTranscript.exe --check » dans un terminal pour le détail ; si un antivirus bloque une DLL, "
                "il faut l'autoriser pour Snappy Transcript.")
    return ("L'identification des intervenants ne se charge pas (" + cause + "). "
            "Relancez install.bat (sans « leger ») ou « pip install -r backend/requirements-diarization.txt ».")
_CHARGEMENT={'fini':False,'erreur':None}
def prechauffer():
    """Charge pyannote et PyTorch en arrière-plan au démarrage : la première identification est plus rapide, et
    l'interface sait tout de suite si ces briques ne se chargent pas sur ce poste (DLL bloquée, installation partielle)."""
    import importlib.util, threading
    if _CHARGEMENT.get('lance'):return
    _CHARGEMENT['lance']=True
    try:present=importlib.util.find_spec('pyannote.audio') is not None and importlib.util.find_spec('torch') is not None
    except (ImportError,ValueError):present=False
    if not present:_CHARGEMENT['fini']=True;return
    def charger():
        try:
            import torch  # noqa: F401
            from pyannote.audio import Pipeline  # noqa: F401
        except Exception as exc:  # noqa: BLE001 — ImportError, OSError (DLL)…
            _CHARGEMENT['erreur']=_absente(exc)
        finally:_CHARGEMENT['fini']=True
    threading.Thread(target=charger,name='prechauffage-intervenants',daemon=True).start()
def erreur_chargement():
    return _CHARGEMENT['erreur']
def chargement_fini():
    return bool(_CHARGEMENT['fini'])
# Étapes de pyannote (noms techniques anglais) traduites pour la barre de progression
ETAPES={'segmentation':'Repérage des passages de parole','speaker_counting':'Comptage des voix',
        'embeddings':'Comparaison des voix','discrete_diarization':'Regroupement par personne'}
def etape(nom):
    return ETAPES.get(str(nom),str(nom).replace('_',' '))
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
    except ImportError as exc:raise RuntimeError(_absente(exc)) from exc
    return Pipeline.from_pretrained(detail)
class Interrompue(Exception):
    """Identification arrêtée à la demande (bouton « Arrêter ») : le texte sans intervenants reste intact."""
def diarize_waveform(waveform,sample_rate,segments,model_path,min_speakers=None,max_speakers=None,progress_callback=None,should_stop=None):
    """segments : liste, ou fonction qui la renvoie (lue à la fin, pour tenir compte des corrections faites entre-temps).
    should_stop : fonction ; si elle renvoie vrai, l'identification s'arrête à la prochaine étape (Interrompue)."""
    def verifier():
        if should_stop and should_stop():raise Interrompue('Identification arrêtée.')
    try:import torch
    except ImportError as exc:raise RuntimeError(_absente(exc)) from exc
    verifier()
    p=_pipeline(model_path); verifier(); tensor=torch.from_numpy(waveform.astype(np.float32,copy=False)).unsqueeze(0)
    kw={}
    if min_speakers:kw['min_speakers']=int(min_speakers)
    if max_speakers:kw['max_speakers']=int(max_speakers)
    class Hook:
        def __init__(self): self.started=time.monotonic(); self.last=0.0
        def __call__(self, step_name, step_artifact=None, file=None, total=None, completed=None, **kwargs):
            # pyannote passes completed/total for iterable pipeline stages.
            verifier()  # hors du try : l'arrêt doit remonter
            if not progress_callback:return
            try:
                c=float(completed or 0); t=float(total or 0); frac=(c/t) if t>0 else None
                now=time.monotonic(); elapsed=now-self.started
                eta=(elapsed/frac-elapsed) if frac and frac>0 else None
                # Throttle UI callbacks slightly; always pass phase changes/final-ish updates.
                if now-self.last>.20 or (frac is not None and frac>=.999):
                    self.last=now; progress_callback(etape(step_name),frac,elapsed,eta)
            except Exception: pass
    hook=Hook() if progress_callback or should_stop else None
    if progress_callback:progress_callback('Préparation',0.0,0.0,None)
    output=p({'waveform':tensor,'sample_rate':int(sample_rate)},hook=hook,**kw) if hook else p({'waveform':tensor,'sample_rate':int(sample_rate)},**kw)
    verifier()
    if progress_callback:progress_callback('Attribution des phrases',1.0,time.monotonic()-hook.started,0.0)
    ann=getattr(output,'exclusive_speaker_diarization',None) or getattr(output,'speaker_diarization',output)
    return _merge(segments() if callable(segments) else segments,_turns(ann))
def diarize_wav_file(wav_path,segments,model_path,min_speakers=None,max_speakers=None,progress_callback=None,should_stop=None):
    """Offline/post-hoc diarization from a PCM16 mono WAV. No browser/base64 and no FFmpeg."""
    with wave.open(str(wav_path),'rb') as f:
        sr=f.getframerate(); ch=f.getnchannels(); sw=f.getsampwidth(); pcm=f.readframes(f.getnframes())
    if ch!=1 or sw!=2:raise ValueError(f'WAV attendu : mono PCM16. Reçu : {ch} canal(aux), {sw*8} bits.')
    audio=np.frombuffer(pcm,dtype=np.int16).astype(np.float32)/32768.0
    return diarize_waveform(audio,sr,segments,model_path,min_speakers,max_speakers,progress_callback,should_stop)

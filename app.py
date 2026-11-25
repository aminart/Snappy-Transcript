from __future__ import annotations
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
import streamlit as st
from audio.microphone import MicrophoneSource, list_input_devices
from audio.system_audio import SystemAudioSource, MixedAudioSource, list_output_devices
from config import CONFIG
from services.live_session import LiveSession
from transcription.mock import MockProvider
from utils.export import segments_to_srt, segments_to_txt, timestamp
from utils.settings import load_settings, save_setting, SETTINGS_FILE
from utils.sync_player import render_sync_player

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
st.set_page_config(page_title='Audio Transcriber V1.5.7', page_icon='🎙️', layout='wide')
saved_settings = load_settings()
for key, value in {'session': None, 'last_error': '', 'stamp': None, 'model_path_input': saved_settings.get('model_path', os.environ.get('WHISPER_MODEL_PATH', ''))}.items():
    if key not in st.session_state: st.session_state[key] = value

st.title('🎙️ Audio Transcriber')
st.caption('V1.5.7 · Pause/Reprise + exports RAW immédiats + diarisation asynchrone + glossaire STT')
try: devices = list_input_devices()
except Exception as exc:
    devices = []
    st.session_state.last_error = f'Périphériques : {exc}'

session = st.session_state.session
busy = bool(session and not session.is_finalized)

with st.sidebar:
    st.header('Source audio')
    source = st.selectbox('Source', ['🎤 Microphone', '🔊 Audio système', '🎤 + 🔊 Micro + audio système', '📁 Fichier audio', '🌐 Stream / URL'], disabled=busy)
    if source in ('📁 Fichier audio', '🌐 Stream / URL'): st.info('Cette source sera ajoutée dans une version suivante.')
    if devices:
        labels = [f"{d['index']} · {d['name']}" for d in devices]
        chosen = st.selectbox('Microphone', labels, disabled=busy)
        device = devices[labels.index(chosen)]
    else:
        device = None
        if source in ('🎤 Microphone','🎤 + 🔊 Micro + audio système'): st.warning('Aucun microphone détecté.')
    outputs=list_output_devices()
    output_name=None
    if source in ('🔊 Audio système','🎤 + 🔊 Micro + audio système'):
        if outputs:
            output_name=st.selectbox('Sortie Windows à capturer', [x['name'] for x in outputs], disabled=busy, help='Capture WASAPI loopback : son Teams/Jabber/navigateur tel qu’il sort du PC.')
        else: st.warning('Aucune sortie système détectée. Vérifie que le paquet soundcard est installé.')
    st.header('Transcription')
    mode = st.selectbox('Moteur', ['Local Whisper (réel)', 'Mock (test)'], disabled=busy)
    model_path = st.text_input('Dossier du modèle faster-whisper / CTranslate2',
                               key='model_path_input',
                               placeholder=r'C:\Users\...\faster-whisper-small',
                               help='Le dernier chemin valide utilisé est mémorisé dans ton profil Windows et restauré aux prochains lancements.',
                               disabled=busy)
    model_validation = None
    if mode.startswith('Local'):
        from transcription.local_whisper import validate_ctranslate2_model
        model_validation = validate_ctranslate2_model(model_path)
        if model_validation.valid:
            st.success(f'✓ Modèle local détecté : {model_validation.path.name}')
            if str(saved_settings.get('model_path', '')) == str(model_validation.path):
                st.caption('Chemin mémorisé comme valeur par défaut.')
        elif model_path:
            st.warning(model_validation.message)
            if model_validation.missing:
                st.caption('Manquants : ' + ', '.join(model_validation.missing))
        else:
            st.info('Renseigne le dossier de ton faster-whisper-small, ou utilise Mock pour tester sans STT.')
    st.header('Accélération')
    acceleration_options = ['Automatique', 'GPU NVIDIA', 'CPU']
    saved_acceleration = saved_settings.get('acceleration', 'Automatique')
    acceleration = st.radio('Moteur de calcul', acceleration_options, index=acceleration_options.index(saved_acceleration) if saved_acceleration in acceleration_options else 0, horizontal=True, disabled=busy,
                            help='Automatique utilise CUDA/FP16 pour faster-whisper si le GPU et les runtimes locaux sont prêts, sinon CPU/int8.')
    cuda_status = None
    if mode.startswith('Local'):
        try:
            from transcription.cuda_runtime import prepare_cuda_runtime
            cuda_status = prepare_cuda_runtime()
            if cuda_status.ready: st.success(f'✓ CUDA prêt · {cuda_status.gpu_count} GPU · cuBLAS 12 · cuDNN 9')
            elif acceleration == 'GPU NVIDIA': st.warning(cuda_status.detail)
            else: st.caption('GPU non prêt : fallback CPU disponible. ' + cuda_status.detail)
        except Exception as exc:
            if acceleration == 'GPU NVIDIA': st.warning(f'Détection CUDA : {type(exc).__name__}: {exc}')

    language = st.selectbox('Langue', ['fr', 'en', 'auto'], disabled=busy)
    glossary = st.text_area('Glossaire métier / noms propres', value=saved_settings.get('stt_glossary', ''), height=100, disabled=busy, placeholder='Ex. A.V., Jabber, RTX A1000, nom de projet, stations, acronymes…', help='Termes à favoriser pendant le décodage Whisper. Sépare-les par virgules, espaces ou retours à la ligne. Privilégie une liste courte et spécifique plutôt qu’un dictionnaire général.')
    chunk_seconds = st.slider('Durée des chunks (secondes)', 3, 15, 5, disabled=busy)
    overlap_seconds = st.slider('Recouvrement entre chunks (secondes)', 0.0, min(2.0, float(chunk_seconds)-0.5), 0.75, 0.25, disabled=busy, help='Redonne du contexte à Whisper autour des coupures. La V1.3 déduplique ensuite les mots répétés.')
    vad_filter = st.toggle('VAD Whisper (ignorer les silences)', value=True, disabled=busy)
    save_audio = st.toggle('Conserver le WAV', value=True, disabled=busy)
    show_timestamps = st.toggle('Afficher les timestamps', value=True)
    st.header('Diarisation')
    diar_mode = st.selectbox('Locuteurs', ['Local pyannote (post-traitement)', 'Désactivée'], disabled=busy,
                             help='V1.5 utilise un vrai pipeline de diarisation local après STOP. Aucun faux speaker heuristique.')
    diar_path = st.text_input('Dossier pipeline pyannote local', value=saved_settings.get('diarization_model_path', ''),
                              placeholder=r'.\models\pyannote-speaker-diarization-community-1', disabled=busy)
    diar_valid = False
    if diar_mode.startswith('Local'):
        from diarization.local_pyannote import validate_diarization_model
        diar_valid, diar_detail = validate_diarization_model(diar_path)
        if diar_valid: st.success('✓ Pipeline Community-1 local détecté et complet')
        elif diar_path: st.warning(diar_detail)
        else: st.info('Renseigne un pipeline pyannote déjà présent sur le disque. La transcription fonctionne sans lui.')
    speaker_hint = st.number_input('Nombre de locuteurs (0 = auto)', min_value=0, max_value=20, value=0, disabled=busy)

    with st.expander('Advanced / Debug'):
        st.write('Sample rate', f'{CONFIG.sample_rate} Hz')
        st.write('Audio device', device['name'] if device else '—')
        st.write('System output', output_name or '—')
        st.write('Chunk duration', f'{chunk_seconds} s')
        st.write('Overlap', f'{overlap_seconds:.2f} s')
        st.write('VAD', 'ON' if vad_filter else 'OFF')
        st.write('Queue size', session.queue_size if session else 0)
        st.write('Chunks processed', session.stats.chunks_processed if session else 0)
        st.write('Last STT latency', f'{session.stats.last_latency:.2f} s' if session else '—')
        st.write('Last chunk audio', f'{session.stats.last_chunk_duration:.2f} s' if session else '—')
        st.write('Real-time ratio', f'{session.stats.realtime_ratio:.2f}×' if session else '—')
        st.write('Average RT ratio', f'{session.stats.average_realtime_ratio:.2f}×' if session else '—')
        st.write('Duplicate words removed', session.stats.duplicate_words_removed if session else 0)
        st.caption('Ratio < 1× : transcription plus rapide que le temps réel. Ratio > 1× : le STT accumule du retard.')
        st.write('faster-whisper', getattr(session.provider, 'faster_whisper_version', '—') if session else '—')
        st.write('CTranslate2', getattr(session.provider, 'ctranslate2_version', '—') if session else '—')
        st.write('Calcul STT', (f"{getattr(session.provider,'device','?').upper()} · {getattr(session.provider,'compute_type','?')}" if session and hasattr(session.provider, 'model') else '—'))
        st.write('Fallback accélération', getattr(session.provider, 'acceleration_fallback', None) or '—' if session else '—')
        st.write('Decoder micro', 'NumPy direct (PyAV bypassé)' if session and hasattr(session.provider, 'model') else '—')
        st.write('Model path', str(model_validation.path) if model_validation and model_validation.path else '—')
        st.write('Model status', 'READY' if model_validation and model_validation.valid else ('NOT REQUIRED' if mode.startswith('Mock') else 'NOT READY'))
        st.write('Settings file', str(SETTINGS_FILE))
        st.write('Crash cache', str(session.cache.path) if session else 'créé au START')
        st.write('Last error', session.stats.last_error if session else st.session_state.last_error or '—')

start_col, pause_col, stop_col = st.columns(3)
with start_col:
    start = st.button('▶ START', type='primary', use_container_width=True,
                      disabled=busy or source in ('📁 Fichier audio','🌐 Stream / URL') or (source in ('🎤 Microphone','🎤 + 🔊 Micro + audio système') and device is None) or (source in ('🔊 Audio système','🎤 + 🔊 Micro + audio système') and not output_name) or (mode.startswith('Local') and (model_validation is None or not model_validation.valid)))
with pause_col:
    pause_resume = st.button('▶ REPRENDRE' if session and session.is_paused else '⏸ PAUSE', use_container_width=True,
                             disabled=not session or session.is_finalized or session._stop.is_set())
with stop_col:
    stop = st.button('■ STOP', use_container_width=True,
                     disabled=not session or session.is_finalized or session._stop.is_set())

if start:
    try:
        if mode.startswith('Local'):
            from transcription.local_whisper import LocalWhisperProvider
            with st.spinner('Chargement du modèle local (GPU si disponible, sinon CPU)...'):
                provider = LocalWhisperProvider(model_path, vad_filter=vad_filter, acceleration=acceleration, glossary=glossary)
            save_setting('model_path', str(model_validation.path))
            save_setting('acceleration', acceleration)
            save_setting('stt_glossary', glossary)
        else: provider = MockProvider()
        microphone = MicrophoneSource(device=device['index'], sample_rate=CONFIG.sample_rate, channels=1, block_ms=CONFIG.block_ms) if device else None
        system_audio = SystemAudioSource(output_name, sample_rate=CONFIG.sample_rate, channels=1, block_ms=CONFIG.block_ms) if output_name else None
        if source == '🎤 Microphone': audio_source=microphone
        elif source == '🔊 Audio système': audio_source=system_audio
        else: audio_source=MixedAudioSource(microphone,system_audio,sample_rate=CONFIG.sample_rate,block_ms=CONFIG.block_ms)
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        new_session = LiveSession(audio_source, provider, chunk_seconds, language, save_audio,
                                  overlap_seconds=overlap_seconds, session_id=stamp)
        new_session.auto_diarization = bool(diar_mode.startswith('Local') and diar_valid)
        new_session.diarization_model_path = diar_path
        new_session.diarization_speaker_hint = int(speaker_hint)
        new_session.diarization_status = 'PENDING' if new_session.auto_diarization else 'DISABLED'
        new_session.raw_segments = None
        new_session.diarized_segments = None
        new_session.raw_txt_path = None
        new_session.raw_srt_path = None
        new_session.diarized_txt_path = None
        new_session.diarized_srt_path = None
        new_session._diarization_thread = None
        if diar_path: save_setting('diarization_model_path', diar_path)
        new_session.start()
        st.session_state.session = new_session
        st.session_state.stamp = stamp
        st.session_state.last_error = ''
        st.rerun()
    except Exception as exc:
        st.session_state.last_error = f'{type(exc).__name__}: {exc}'
if pause_resume and session:
    session.resume() if session.is_paused else session.pause()
    st.rerun()

if stop and session:
    try: session.stop()
    except Exception as exc: st.session_state.last_error = f'{type(exc).__name__}: {exc}'
    st.rerun()

@st.fragment(run_every='1s')
def live_view():
    """Zone volontairement dynamique : uniquement pendant capture/finalisation STT.

    Le lecteur audio final n'est jamais créé dans ce fragment afin qu'un rerun
    périodique Streamlit ne puisse pas réinitialiser sa position de lecture.
    """
    s = st.session_state.session
    if not s:
        st.info('Choisis un microphone et un moteur, puis clique sur START.')
        return
    if s.is_finalized:
        # Quitte le fragment périodique et reconstruit une seule fois la vue finale statique.
        st.rerun()
        return

    a,b,c,d,e = st.columns(5)
    a.metric('Status', s.status)
    b.metric('Recording duration', f'{s.duration:.1f} s')
    c.metric('Chunks processed', s.stats.chunks_processed)
    d.metric('RT ratio', f'{s.stats.realtime_ratio:.2f}×' if s.stats.chunks_processed else '—')
    e.metric('Queue', s.queue_size)
    st.subheader('TRANSCRIPTION LIVE')
    st.caption('Texte consolidé au fil des fenêtres. Le recouvrement améliore les coupures de phrases ; les répétitions exactes sont supprimées automatiquement.')
    segs = s.segments()
    if segs:
        live_text = segments_to_txt(segs) if show_timestamps else '\n'.join(x.text for x in segs)
        if len(live_text) > 50000:
            st.caption('Affichage live limité aux ~50 000 derniers caractères pour les longues réunions. Le cache contient tout le texte.')
            live_text = live_text[-50000:]
        st.code(live_text, language=None)
    else:
        st.info('En attente du premier chunk transcrit...')
    if s.stats.last_error:
        st.error(s.stats.last_error)
    if s.is_paused:
        st.info('⏸ En pause : audio ignoré. REPRENDRE continue le même WAV et la même session.')
    elif s._stop.is_set():
        st.warning('Arrêt de la capture effectué. Finalisation des derniers chunks STT en cours…')


def _prepare_raw_exports(s, stamp):
    """Freeze the non-diarized transcript as soon as STT finalization completes."""
    if getattr(s, 'raw_segments', None) is not None:
        return
    raw = s.segments()
    s.raw_segments = list(raw)
    s.raw_txt_path = s.session_dir / f'transcript_{stamp}_raw.txt'
    s.raw_srt_path = s.session_dir / f'transcript_{stamp}_raw.srt'
    s.raw_txt_path.write_text(segments_to_txt(raw), encoding='utf-8')
    s.raw_srt_path.write_text(segments_to_srt(raw), encoding='utf-8')


def _diarization_worker(s, model_path, speaker_hint):
    """Background worker: never calls Streamlit APIs."""
    try:
        from diarization.local_pyannote import diarize_wav_file
        s.diarization_status = 'RUNNING'
        kwargs={'min_speakers':speaker_hint,'max_speakers':speaker_hint} if speaker_hint else {}
        labelled=diarize_wav_file(s.wav_path, list(s.raw_segments or s.segments()), model_path, **kwargs)
        s.diarized_segments=list(labelled)
        # use actual session filename stem; the worker never touches Streamlit state
        stem=s.wav_path.stem.replace('recording_','')
        s.diarized_txt_path=s.session_dir/f'transcript_{stem}_diarized.txt'
        s.diarized_srt_path=s.session_dir/f'transcript_{stem}_diarized.srt'
        s.diarized_txt_path.write_text(segments_to_txt(labelled),encoding='utf-8')
        s.diarized_srt_path.write_text(segments_to_srt(labelled),encoding='utf-8')
        s.diarization_status='DONE'
    except Exception as exc:
        s.diarization_status='ERROR'
        s.stats.last_error=f'Diarisation : {type(exc).__name__}: {exc}'


def _start_diarization_background(s, model_path, speaker_hint):
    th=getattr(s,'_diarization_thread',None)
    if th and th.is_alive(): return
    th=threading.Thread(target=_diarization_worker,args=(s,model_path,speaker_hint),name='diarization-worker',daemon=True)
    s._diarization_thread=th; th.start()


@st.fragment(run_every='2s')
def diarization_status_view():
    s=st.session_state.session
    if not s or not s.is_finalized: return
    status=getattr(s,'diarization_status','DISABLED')
    if status=='RUNNING':
        st.info('👥 Diarisation en cours en arrière-plan. Les exports RAW ci-dessus restent immédiatement utilisables.')
    elif status=='DONE':
        st.success('✓ Diarisation terminée. Les exports avec locuteurs sont prêts.')
        if s.diarized_txt_path and s.diarized_txt_path.exists():
            st.download_button('⬇ TXT diarizé',s.diarized_txt_path.read_bytes(),s.diarized_txt_path.name,'text/plain',key='async_diar_txt')
        if s.diarized_srt_path and s.diarized_srt_path.exists():
            st.download_button('⬇ SRT diarizé',s.diarized_srt_path.read_bytes(),s.diarized_srt_path.name,'text/plain',key='async_diar_srt')
    elif status=='ERROR':
        st.warning('La diarisation a échoué ; les exports RAW restent intacts.')
        if s.stats.last_error: st.error(s.stats.last_error)


def finalized_view(s):
    """Post-STOP: raw artifacts first, stable player, diarization in background."""
    stamp=st.session_state.stamp or 'session'
    _prepare_raw_exports(s,stamp)
    raw=list(s.raw_segments or [])
    st.success('Session terminée : WAV + transcription RAW disponibles immédiatement.')

    st.subheader('EXPORTS IMMÉDIATS · SANS DIARISATION')
    c1,c2,c3=st.columns(3)
    if s.save_audio and s.wav_path.exists():
        size_mb=s.wav_path.stat().st_size/(1024*1024)
        if size_mb < 100: c1.download_button('⬇ Audio WAV',s.wav_path.read_bytes(),s.wav_path.name,'audio/wav',key='raw_wav')
        else: c1.caption(f'WAV {size_mb:.1f} MiB conservé sur disque')
    c2.download_button('⬇ TXT RAW',s.raw_txt_path.read_bytes(),s.raw_txt_path.name,'text/plain',key='raw_txt')
    c3.download_button('⬇ SRT RAW',s.raw_srt_path.read_bytes(),s.raw_srt_path.name,'text/plain',key='raw_srt')
    st.caption(f'Fichiers RAW persistants : {s.session_dir}')

    if s.save_audio and s.wav_path.exists():
        st.subheader('AUDIO + TRANSCRIPTION SYNCHRONISÉE · RAW')
        render_sync_player(s.wav_path,raw)
        st.caption('Ce lecteur reste sur la transcription RAW et n’est pas reconstruit par le suivi de diarisation.')

    enabled=bool(getattr(s,'auto_diarization',False)) and s.wav_path.exists()
    if enabled:
        st.subheader('DIARISATION')
        status=getattr(s,'diarization_status','PENDING')
        if status=='PENDING':
            _start_diarization_background(s,getattr(s,'diarization_model_path',diar_path),int(getattr(s,'diarization_speaker_hint',0) or 0))
        elif status in ('ERROR','DONE'):
            if st.button('👥 Relancer la diarisation locale',key='rerun_diar_async'):
                s.diarization_status='PENDING'; s.diarized_segments=None
                _start_diarization_background(s,getattr(s,'diarization_model_path',diar_path),int(getattr(s,'diarization_speaker_hint',0) or 0))
        diarization_status_view()
    else:
        st.caption('Diarisation désactivée pour cette session.')
    st.caption(f'Copie de récupération live : {s.cache.path}')


if session and session.is_finalized:
    finalized_view(session)
else:
    live_view()

st.divider()
st.subheader('♻️ Reprise / diarisation après coup')
st.caption('Pour une longue réunion existante, indique les chemins locaux : aucun gros fichier ne transite par le WebSocket Streamlit.')
with st.expander('Diariser un WAV + SRT existants'):
    recover_wav = st.text_input('Chemin du WAV existant', placeholder=r'C:\...\recording.wav', key='recover_wav')
    recover_srt = st.text_input('Chemin du SRT existant', placeholder=r'C:\...\transcript.srt', key='recover_srt')
    recover_speakers = st.number_input('Nombre de locuteurs pour cette reprise (0 = auto)',0,20,0,key='recover_speakers')
    if st.button('👥 Diariser après coup', key='posthoc_diarize'):
        try:
            from pathlib import Path
            from diarization.local_pyannote import diarize_wav_file, validate_diarization_model
            from utils.import_transcript import parse_srt
            wp,sp=Path(recover_wav.strip().strip('"')),Path(recover_srt.strip().strip('"'))
            if not wp.is_file(): raise FileNotFoundError(f'WAV introuvable : {wp}')
            if not sp.is_file(): raise FileNotFoundError(f'SRT introuvable : {sp}')
            ok,detail=validate_diarization_model(diar_path)
            if not ok: raise ValueError(detail)
            original=parse_srt(sp.read_text(encoding='utf-8-sig'))
            kwargs={'min_speakers':int(recover_speakers),'max_speakers':int(recover_speakers)} if recover_speakers else {}
            progress=st.progress(0, text='Préparation de la diarisation…')
            def on_progress(phase, frac, elapsed, eta):
                pct=max(0,min(100,int((frac or 0)*100)))
                eta_txt=f' · reste estimé ~{int(eta//60)} min {int(eta%60):02d} s' if eta is not None else ''
                progress.progress(pct, text=f'{phase} · {pct}% · écoulé {int(elapsed//60)}:{int(elapsed%60):02d}{eta_txt}')
            labelled=diarize_wav_file(wp,original,diar_path,progress_callback=on_progress,**kwargs)
            progress.progress(100,text='Diarisation terminée')
            out_txt=wp.with_name(wp.stem+'_diarized.txt'); out_srt=wp.with_name(wp.stem+'_diarized.srt')
            out_txt.write_text(segments_to_txt(labelled),encoding='utf-8'); out_srt.write_text(segments_to_srt(labelled),encoding='utf-8')
            st.success(f'Diarisation terminée : {len(labelled)} segments. Fichiers écrits à côté du WAV.')
            st.code(str(out_txt)+'\n'+str(out_srt),language=None)
            st.download_button('⬇ TXT diarizé',out_txt.read_bytes(),out_txt.name,'text/plain',key='post_txt')
            st.download_button('⬇ SRT diarizé',out_srt.read_bytes(),out_srt.name,'text/plain',key='post_srt')
        except Exception as exc:
            st.error(f'Reprise : {type(exc).__name__}: {exc}')

if st.session_state.last_error: st.error(st.session_state.last_error)
st.caption('V1.5.7 · Confidentialité : STT et diarisation configurée ici sont locaux. Aucun audio n’est envoyé sur le réseau par l’application.')

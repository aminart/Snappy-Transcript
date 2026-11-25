"""Orchestration d'une session : démarrage, exports bruts, diarisation en arrière-plan, reprise après coup.

Contrairement à l'ancienne interface Streamlit, rien ici ne dépend d'un navigateur ouvert : un thread de
finalisation écrit les exports dès que la transcription est terminée, et la diarisation tourne ensuite seule.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .audio.microphone import MicrophoneSource
from .audio.system_audio import MixedAudioSource, SystemAudioSource
from .config import CONFIG
from .export import segments_to_srt, segments_to_txt
from .file_session import FileTranscription
from .models import TranscriptSegment
from .paths import app_data_dir
from .session import LiveSession
from .srt import parse_srt
from .transcription.mock import MockProvider

log = logging.getLogger(__name__)

# pyannote est lourd (mémoire, CPU) : une seule diarisation à la fois, les autres attendent leur tour.
_DIARIZATION_LOCK = threading.Lock()


class ServiceError(Exception):
    """Erreur destinée à l'utilisateur, avec le code HTTP à renvoyer."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class StartParams:
    source: str = "microphone"           # microphone | system | mixed
    engine: str = "local"                # local | mock
    input_device: int | None = None
    output_device: str = ""
    model_path: str = ""
    acceleration: str = "auto"
    language: str = "fr"
    glossary: str = ""
    chunk_seconds: int = 5
    overlap_seconds: float = 0.75
    vad_filter: bool = True
    save_audio: bool = True
    diarization: bool = True
    diarization_model_path: str = ""
    speaker_hint: int = 0


def segment_to_dict(seg: TranscriptSegment, words: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text, "speaker": seg.speaker}
    if words:
        out["words"] = [[round(w.start, 3), round(w.end, 3), w.text] for w in seg.words]
    return out


# --- Diarisation --------------------------------------------------------------------------------------------

class DiarizationJob:
    """Suivi d'une diarisation (de la session courante ou d'une reprise après coup)."""

    def __init__(self) -> None:
        self.status = "IDLE"          # IDLE | RUNNING | DONE | ERROR
        self.phase = ""
        self.fraction: float | None = None
        self.elapsed = 0.0
        self.eta: float | None = None
        self.error = ""
        self.note = ""
        self.thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.status == "RUNNING"

    def progress(self, phase: str, fraction: float | None, elapsed: float, eta: float | None) -> None:
        self.phase, self.fraction, self.elapsed, self.eta = phase, fraction, elapsed, eta

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "phase": self.phase, "fraction": self.fraction, "elapsed": round(self.elapsed, 1),
                "eta": None if self.eta is None else round(self.eta, 1), "error": self.error, "note": self.note}


def _diarize(wav: Path, segments: list[TranscriptSegment], model_path: str, speakers: int, job: DiarizationJob) -> list[TranscriptSegment]:
    from .diarization import diarize_wav_file

    kwargs = {"min_speakers": speakers, "max_speakers": speakers} if speakers else {}
    job.progress("en attente d'une autre diarisation", None, 0.0, None)
    with _DIARIZATION_LOCK:
        return diarize_wav_file(wav, segments, model_path, progress_callback=job.progress, **kwargs)


def _validate_pipeline(path: str) -> str:
    from .diarization import validate_diarization_model

    ok, detail = validate_diarization_model(path)
    if not ok:
        raise ServiceError(detail, 422)
    return detail


# --- Session active -----------------------------------------------------------------------------------------

class ActiveSession:
    def __init__(self, live: LiveSession, stamp: str, params: StartParams, provider: Any, diarization_note: str = ""):
        self.live, self.stamp, self.params, self.provider = live, stamp, params, provider
        self.diar = DiarizationJob()
        self.diar.note = diarization_note
        self.diar_wanted = False                      # diarisation automatique à lancer après la transcription
        self.diar_model_path = ""
        self.raw_segments: list[TranscriptSegment] | None = None
        self.diarized_segments: list[TranscriptSegment] | None = None
        self.raw_txt = self.raw_srt = self.diar_txt = self.diar_srt = None
        self._exports_done = threading.Event()
        self._lock = threading.RLock()

    @property
    def finished(self) -> bool:
        """Capture et transcription terminées ET exports écrits : c'est à partir de là que tout est téléchargeable."""
        return self.live.is_finalized and self._exports_done.is_set()

    # -- finalisation : indépendante de l'interface ------------------------------------------------------------

    def watch(self) -> None:
        threading.Thread(target=self._finalize_when_done, name="finalizer", daemon=True).start()

    def _finalize_when_done(self) -> None:
        while not self.live.is_finalized:
            time.sleep(0.2)
        try:
            self._write_raw_exports()
            if self.diar_wanted and self.live.wav_path.is_file() and self.raw_segments:
                self.start_diarization(self.diar_model_path, self.params.speaker_hint)
            else:
                self._discard_wav_if_unwanted()
        except Exception as exc:  # ne jamais perdre silencieusement la fin de session
            log.exception("Finalisation de session")
            self.live.stats.last_error = f"Finalisation : {type(exc).__name__}: {exc}"
        finally:
            self._exports_done.set()

    def _write_raw_exports(self) -> None:
        with self._lock:
            if self.raw_segments is not None:
                return
            raw = self.live.segments()
            self.raw_txt = self.live.session_dir / f"transcript_{self.stamp}_raw.txt"
            self.raw_srt = self.live.session_dir / f"transcript_{self.stamp}_raw.srt"
            self.raw_txt.write_text(segments_to_txt(raw), encoding="utf-8")
            self.raw_srt.write_text(segments_to_srt(raw), encoding="utf-8")
            self.raw_segments = raw

    def _discard_wav_if_unwanted(self) -> None:
        """« Conserver le WAV » décoché : l'enregistrement n'est gardé que le temps dont la diarisation a besoin."""
        if not self.params.save_audio:
            self.live.wav_path.unlink(missing_ok=True)

    # -- diarisation ---------------------------------------------------------------------------------------------

    def start_diarization(self, model_path: str, speakers: int = 0) -> None:
        with self._lock:
            if self.diar.running:
                raise ServiceError("Une diarisation est déjà en cours pour cette session.", 409)
            if not self.live.wav_path.is_file():
                raise ServiceError("L'enregistrement WAV de cette session n'existe plus : diarisation impossible.", 409)
            model = _validate_pipeline(model_path)
            job = self.diar
            job.status, job.error, job.fraction, job.phase = "RUNNING", "", None, "préparation"
            job.thread = threading.Thread(target=self._diarize_worker, args=(model, speakers), name="diarization", daemon=True)
            job.thread.start()

    def _diarize_worker(self, model: str, speakers: int) -> None:
        job = self.diar
        try:
            labelled = _diarize(self.live.wav_path, list(self.raw_segments or self.live.segments()), model, speakers, job)
            self.diar_txt = self.live.session_dir / f"transcript_{self.stamp}_diarized.txt"
            self.diar_srt = self.live.session_dir / f"transcript_{self.stamp}_diarized.srt"
            self.diar_txt.write_text(segments_to_txt(labelled), encoding="utf-8")
            self.diar_srt.write_text(segments_to_srt(labelled), encoding="utf-8")
            self.diarized_segments = labelled
            job.status = "DONE"
            self._discard_wav_if_unwanted()
        except Exception as exc:
            log.exception("Diarisation")
            job.status, job.error = "ERROR", f"{type(exc).__name__}: {exc}"

    # -- état renvoyé à l'interface ------------------------------------------------------------------------------

    def files(self) -> dict[str, bool]:
        def ok(p: Path | None) -> bool:
            return bool(p and p.is_file())
        return {"wav": self.live.wav_path.is_file(), "raw_txt": ok(self.raw_txt), "raw_srt": ok(self.raw_srt),
                "diarized_txt": ok(self.diar_txt), "diarized_srt": ok(self.diar_srt)}

    def provider_info(self) -> dict[str, str]:
        p = self.provider
        if not hasattr(p, "model"):
            return {"engine": "Simulation"}
        return {"engine": "faster-whisper", "faster_whisper": getattr(p, "faster_whisper_version", ""),
                "ctranslate2": getattr(p, "ctranslate2_version", ""),
                "compute": f"{getattr(p, 'device', '?').upper()} · {getattr(p, 'compute_type', '?')}",
                "fallback": getattr(p, "acceleration_fallback", None) or ""}

    def state(self, after: int = 0) -> dict[str, Any]:
        live = self.live
        segments = live.segments()
        start_index = after if 0 <= after <= len(segments) else 0   # le client en sait trop : il repart de zéro
        stats = live.stats
        return {
            "active": True, "id": self.stamp, "kind": getattr(live, "kind", "live"),
            "file": live.progress_info() if hasattr(live, "progress_info") else None, "status": live.status, "paused": live.is_paused,
            "stopping": live.stop_requested, "finalized": self.finished,
            "duration": round(live.duration, 1), "queue": live.queue_size,
            "stats": {"chunks": stats.chunks_processed, "last_latency": round(stats.last_latency, 2),
                      "last_chunk_duration": round(stats.last_chunk_duration, 2), "realtime_ratio": round(stats.realtime_ratio, 2),
                      "average_realtime_ratio": round(stats.average_realtime_ratio, 2),
                      "duplicate_words_removed": stats.duplicate_words_removed},
            "error": stats.last_error, "provider": self.provider_info(),
            "from": start_index, "total": len(segments),
            "segments": [segment_to_dict(s) for s in segments[start_index:]],
            "diarization": {**self.diar.as_dict(), "wanted": self.diar_wanted},
            "files": self.files() if self.finished else {},
            "session_dir": str(live.session_dir), "recovery_copy": str(live.cache.path),
            "save_audio": self.params.save_audio,
        }

    def transcript(self, variant: str) -> list[dict[str, Any]]:
        if variant == "diarized":
            if self.diarized_segments is None:
                raise ServiceError("La transcription avec locuteurs n'est pas encore prête.", 404)
            segs = self.diarized_segments
        else:
            segs = self.raw_segments if self.raw_segments is not None else self.live.segments()
        return [segment_to_dict(s, words=True) for s in segs]

    def file_path(self, kind: str) -> Path:
        mapping = {"wav": self.live.wav_path, "raw_txt": self.raw_txt, "raw_srt": self.raw_srt,
                   "diarized_txt": self.diar_txt, "diarized_srt": self.diar_srt}
        path = mapping.get(kind)
        if not path or not path.is_file():
            raise ServiceError("Ce fichier n'est pas (ou plus) disponible.", 404)
        return path


# --- Reprise après coup (WAV + SRT déjà sur le disque) ------------------------------------------------------

class PosthocJob(DiarizationJob):
    def __init__(self) -> None:
        super().__init__()
        self.outputs: dict[str, Path] = {}
        self.segments = 0

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), "segments": self.segments, "outputs": {k: str(v) for k, v in self.outputs.items()}}


def _clean_path(raw: str) -> Path:
    return Path((raw or "").strip().strip('"')).expanduser()


# --- Fichiers envoyés par le navigateur ---------------------------------------------------------------------
# Le navigateur et le serveur sont sur le même PC : l'envoi est une simple copie locale, rien ne passe par le réseau.

_UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{16,64}(\.[a-z0-9]{1,8})?")
UPLOAD_MAX_AGE = 24 * 3600


def uploads_dir() -> Path:
    return app_data_dir() / "uploads"


def new_upload(name: str) -> tuple[str, Path]:
    """Identifiant et chemin d'un nouveau fichier envoyé ; nettoie au passage les envois abandonnés de plus d'un jour."""
    folder = uploads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    limite = time.time() - UPLOAD_MAX_AGE
    for old in folder.iterdir():
        try:
            if old.stat().st_mtime < limite:
                old.unlink()
        except OSError:
            pass
    suffix = Path(name).suffix.lower()
    suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""
    upload_id = secrets.token_urlsafe(18) + suffix
    (folder / f"{upload_id}.name").write_text(Path(name).name[:200] or "fichier", encoding="utf-8")
    return upload_id, folder / upload_id


def uploaded_file(upload_id: str) -> Path:
    if not _UPLOAD_ID.fullmatch(upload_id or ""):
        raise ServiceError("Envoi inconnu.", 404)
    path = uploads_dir() / upload_id
    if not path.is_file():
        raise ServiceError("Le fichier envoyé n'est plus disponible : choisissez-le à nouveau.", 404)
    return path


def upload_name(upload_id: str) -> str:
    try:
        return (uploads_dir() / f"{upload_id}.name").read_text(encoding="utf-8").strip() or upload_id
    except OSError:
        return upload_id


# --- Gestionnaire --------------------------------------------------------------------------------------------

class Manager:
    def __init__(self) -> None:
        self.current: ActiveSession | None = None
        self.posthoc = PosthocJob()
        self._lock = threading.RLock()

    # -- sessions ------------------------------------------------------------------------------------------------

    def _new_stamp(self) -> str:
        base = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        stamp, n = base, 1
        while (app_data_dir() / "sessions" / stamp).exists():  # deux départs dans la même seconde
            n += 1
            stamp = f"{base}-{n}"
        return stamp

    def _provider(self, p: StartParams):
        if p.engine == "mock":
            return MockProvider()
        from .transcription.whisper import LocalWhisperProvider, validate_ctranslate2_model

        check = validate_ctranslate2_model(p.model_path)
        if not check.valid:
            detail = f" Manquants : {', '.join(check.missing)}." if check.missing else ""
            raise ServiceError(check.message + detail, 422)
        try:
            return LocalWhisperProvider(p.model_path, vad_filter=p.vad_filter, acceleration=p.acceleration, glossary=p.glossary)
        except (ValueError, RuntimeError) as exc:
            raise ServiceError(str(exc), 422) from exc

    def _source(self, p: StartParams):
        rate, block = CONFIG.sample_rate, CONFIG.block_ms
        mic = system = None
        if p.source in ("microphone", "mixed"):
            if p.input_device is None:
                raise ServiceError("Aucun microphone sélectionné.", 422)
            mic = MicrophoneSource(device=p.input_device, sample_rate=rate, channels=1, block_ms=block)
        if p.source in ("system", "mixed"):
            system = SystemAudioSource(p.output_device or None, sample_rate=rate, channels=1, block_ms=block)
        if p.source == "microphone":
            return mic
        if p.source == "system":
            return system
        return MixedAudioSource(mic, system, sample_rate=rate, block_ms=block)

    def _check_free(self) -> None:
        if self.current and not self.current.finished:
            raise ServiceError("Une session est déjà en cours.", 409)
        if self.current and self.current.diar.running:
            raise ServiceError("Attendez la fin de la diarisation avant de commencer une nouvelle session.", 409)

    @staticmethod
    def _diarization_choice(p: StartParams) -> tuple[bool, str, str]:
        """(à lancer, dossier du pipeline, note affichée si elle ne sera pas lancée)."""
        if not p.diarization:
            return False, "", ""
        from .diarization import validate_diarization_model
        ok, detail = validate_diarization_model(p.diarization_model_path)
        return (True, detail, "") if ok else (False, "", f"Diarisation non lancée : {detail}")

    def _launch(self, live: Any, stamp: str, p: StartParams, provider: Any) -> dict[str, Any]:
        wanted, model, note = self._diarization_choice(p)
        active = ActiveSession(live, stamp, p, provider, note)
        active.diar_wanted, active.diar_model_path = wanted, model
        try:
            live.start()
        except OSError as exc:
            raise ServiceError(f"Impossible d'ouvrir la source audio : {exc}", 422) from exc
        active.watch()
        self.current = active
        return active.state()

    def start(self, p: StartParams) -> dict[str, Any]:
        with self._lock:
            self._check_free()
            if p.source not in ("microphone", "system", "mixed") or p.engine not in ("local", "mock"):
                raise ServiceError("Source ou moteur inconnu.", 422)
            provider = self._provider(p)
            source = self._source(p)
            stamp = self._new_stamp()
            live = LiveSession(source, provider, p.chunk_seconds, p.language, p.save_audio,
                               overlap_seconds=p.overlap_seconds, session_id=stamp)
            return self._launch(live, stamp, p, provider)

    def start_file(self, p: StartParams, upload_id: str = "", path: str = "") -> dict[str, Any]:
        """Transcription d'un fichier : envoyé par le navigateur (upload_id) ou déjà sur ce PC (path, jamais modifié)."""
        with self._lock:
            self._check_free()
            if upload_id:
                source, name, temporary = uploaded_file(upload_id), upload_name(upload_id), True
            else:
                source, temporary = _clean_path(path), False
                if not str(path).strip():
                    raise ServiceError("Choisissez un fichier.", 422)
                if not source.is_file():
                    raise ServiceError(f"Fichier introuvable : {source}", 422)
                name = source.name
            provider = self._provider(p)
            stamp = self._new_stamp()
            live = FileTranscription(source, provider, p.language, stamp, p.save_audio, display_name=name,
                                     delete_source=temporary)
            return self._launch(live, stamp, p, provider)

    def _need(self) -> ActiveSession:
        if not self.current:
            raise ServiceError("Aucune session.", 404)
        return self.current

    def state(self, after: int = 0) -> dict[str, Any]:
        s = self.current
        return s.state(after) if s else {"active": False}

    def pause(self) -> dict[str, Any]:
        s = self._need()
        if s.finished or s.live.stop_requested:
            raise ServiceError("La session est terminée.", 409)
        s.live.pause()
        return s.state()

    def resume(self) -> dict[str, Any]:
        s = self._need()
        if s.finished or s.live.stop_requested:
            raise ServiceError("La session est terminée.", 409)
        s.live.resume()
        return s.state()

    def stop(self) -> dict[str, Any]:
        s = self._need()
        if not s.live.stop_requested:
            try:
                s.live.stop()
            except RuntimeError as exc:
                raise ServiceError(str(exc), 500) from exc
        return s.state()

    def discard(self) -> None:
        with self._lock:
            s = self.current
            if not s:
                return
            if not s.finished:
                raise ServiceError("La session n'est pas terminée.", 409)
            if s.diar.running:
                raise ServiceError("Attendez la fin de la diarisation avant de commencer une nouvelle session.", 409)
            self.current = None

    def shutdown(self) -> None:
        """Arrêt propre du serveur : referme le WAV de la session en cours pour qu'il reste lisible."""
        s = self.current
        if s and not s.finished and not s.live.stop_requested:
            try:
                s.live.stop()
            except Exception:
                log.exception("Arrêt de la session à la fermeture")

    # -- reprise après coup ---------------------------------------------------------------------------------------

    def start_posthoc(self, wav: str, srt: str, model_path: str, speakers: int) -> dict[str, Any]:
        with self._lock:
            if self.posthoc.running:
                raise ServiceError("Une reprise est déjà en cours.", 409)
            wav_path, srt_path = _clean_path(wav), _clean_path(srt)
            if not wav_path.is_file():
                raise ServiceError(f"WAV introuvable : {wav_path}", 422)
            if not srt_path.is_file():
                raise ServiceError(f"SRT introuvable : {srt_path}", 422)
            model = _validate_pipeline(model_path)
            try:
                original = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ServiceError(f"SRT illisible : {exc}", 422) from exc
            job = self.posthoc = PosthocJob()
            job.status, job.phase = "RUNNING", "préparation"
            job.thread = threading.Thread(target=self._posthoc_worker, args=(job, wav_path, original, model, speakers),
                                          name="posthoc-diarization", daemon=True)
            job.thread.start()
            return job.as_dict()

    @staticmethod
    def _posthoc_worker(job: PosthocJob, wav: Path, original: list[TranscriptSegment], model: str, speakers: int) -> None:
        try:
            labelled = _diarize(wav, original, model, speakers, job)
            txt, srt = wav.with_name(wav.stem + "_diarized.txt"), wav.with_name(wav.stem + "_diarized.srt")
            txt.write_text(segments_to_txt(labelled), encoding="utf-8")
            srt.write_text(segments_to_srt(labelled), encoding="utf-8")
            job.outputs, job.segments = {"txt": txt, "srt": srt}, len(labelled)
            job.status = "DONE"
        except Exception as exc:
            log.exception("Diarisation après coup")
            job.status, job.error = "ERROR", f"{type(exc).__name__}: {exc}"


manager = Manager()

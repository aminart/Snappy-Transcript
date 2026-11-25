"""API REST de Snappy Transcript (sous /api) : réglages, périphériques, session live, exports, reprise après coup."""
from __future__ import annotations

import importlib.util
import sys
from typing import Any, Literal

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .audio.microphone import list_input_devices
from .audio.system_audio import list_output_devices
from .service import ServiceError, StartParams, manager
from .settings import load_settings, save_settings

router = APIRouter(prefix="/api")


def _present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


# --- Environnement -------------------------------------------------------------------------------------------

@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """Ce que cette installation sait faire : permet à l'interface d'expliquer ce qui manque plutôt que d'échouer."""
    return {
        "platform": sys.platform,
        "stt": _present("faster_whisper"),
        "diarization": _present("pyannote.audio") and _present("torch"),
        "system_audio": sys.platform == "win32" and _present("soundcard"),
    }


@router.get("/devices")
def devices() -> dict[str, Any]:
    inputs, input_error = [], ""
    try:
        inputs = list_input_devices()
    except Exception as exc:  # PortAudio absent, aucun périphérique…
        input_error = f"{type(exc).__name__}: {exc}"
    return {"inputs": inputs, "input_error": input_error, "outputs": list_output_devices()}


@router.get("/cuda")
def cuda() -> dict[str, Any]:
    try:
        from .transcription.cuda_runtime import prepare_cuda_runtime
        st = prepare_cuda_runtime()
        return {"ready": st.ready, "gpu_count": st.gpu_count, "detail": st.detail}
    except Exception as exc:
        return {"ready": False, "gpu_count": 0, "detail": f"Détection CUDA : {type(exc).__name__}: {exc}"}


class CheminModele(BaseModel):
    path: str = ""


@router.post("/model/check")
def check_model(body: CheminModele) -> dict[str, Any]:
    from .transcription.whisper import validate_ctranslate2_model
    v = validate_ctranslate2_model(body.path)
    return {"valid": v.valid, "name": v.path.name if v.path else "", "message": v.message, "missing": list(v.missing)}


@router.post("/diarization/check")
def check_diarization(body: CheminModele) -> dict[str, Any]:
    from .diarization import validate_diarization_model
    ok, detail = validate_diarization_model(body.path)
    return {"valid": ok, "message": "Pipeline Community-1 local détecté et complet." if ok else detail}


# --- Réglages ------------------------------------------------------------------------------------------------

@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return load_settings()


@router.put("/settings")
def put_settings(values: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return save_settings(values)


# --- Session live --------------------------------------------------------------------------------------------

class DemandeDemarrage(BaseModel):
    source: Literal["microphone", "system", "mixed"] = "microphone"
    engine: Literal["local", "mock"] = "local"
    input_device: int | None = None
    output_device: str = ""
    model_path: str = ""
    acceleration: Literal["auto", "gpu", "cpu"] = "auto"
    language: Literal["fr", "en", "auto"] = "fr"
    glossary: str = ""
    chunk_seconds: int = Field(5, ge=3, le=15)
    overlap_seconds: float = Field(0.75, ge=0, le=2)
    vad_filter: bool = True
    save_audio: bool = True
    diarization: bool = True
    diarization_model_path: str = ""
    speaker_hint: int = Field(0, ge=0, le=20)


@router.post("/session/start")
def start(body: DemandeDemarrage) -> dict[str, Any]:
    return manager.start(StartParams(**body.model_dump()))


@router.get("/session")
def session(after: int = 0) -> dict[str, Any]:
    """État de la session ; `after` : nombre de segments que le client possède déjà (seuls les suivants sont renvoyés)."""
    return manager.state(after)


@router.post("/session/pause")
def pause() -> dict[str, Any]:
    return manager.pause()


@router.post("/session/resume")
def resume() -> dict[str, Any]:
    return manager.resume()


@router.post("/session/stop")
def stop() -> dict[str, Any]:
    return manager.stop()


@router.delete("/session")
def discard() -> dict[str, bool]:
    manager.discard()
    return {"ok": True}


@router.get("/session/transcript")
def transcript(variant: Literal["raw", "diarized"] = "raw") -> dict[str, Any]:
    if not manager.current:
        raise ServiceError("Aucune session.", 404)
    return {"segments": manager.current.transcript(variant)}


class DemandeDiarisation(BaseModel):
    model_path: str = ""
    speakers: int = Field(0, ge=0, le=20)


@router.post("/session/diarization")
def rerun_diarization(body: DemandeDiarisation) -> dict[str, Any]:
    s = manager.current
    if not s or not s.finished:
        raise ServiceError("La session doit être terminée.", 409)
    s.start_diarization(body.model_path or s.diar_model_path, body.speakers)
    return s.state()


_TYPES = {"wav": "audio/wav", "raw_txt": "text/plain; charset=utf-8", "raw_srt": "text/plain; charset=utf-8",
          "diarized_txt": "text/plain; charset=utf-8", "diarized_srt": "text/plain; charset=utf-8"}


@router.get("/session/file/{kind}")
def session_file(kind: Literal["wav", "raw_txt", "raw_srt", "diarized_txt", "diarized_srt"], download: bool = False) -> FileResponse:
    """Fichiers de la session. Le WAV sert aussi au lecteur : FileResponse gère les requêtes Range (déplacement)."""
    if not manager.current:
        raise ServiceError("Aucune session.", 404)
    path = manager.current.file_path(kind)
    return FileResponse(path, media_type=_TYPES[kind], filename=path.name if download else None)


# --- Reprise après coup --------------------------------------------------------------------------------------

class DemandeReprise(BaseModel):
    wav_path: str
    srt_path: str
    model_path: str = ""
    speakers: int = Field(0, ge=0, le=20)


@router.get("/posthoc")
def posthoc() -> dict[str, Any]:
    return manager.posthoc.as_dict()


@router.post("/posthoc")
def start_posthoc(body: DemandeReprise) -> dict[str, Any]:
    return manager.start_posthoc(body.wav_path, body.srt_path, body.model_path, body.speakers)


@router.get("/posthoc/file/{kind}")
def posthoc_file(kind: Literal["txt", "srt"]) -> FileResponse:
    path = manager.posthoc.outputs.get(kind)
    if not path or not path.is_file():
        raise ServiceError("Ce fichier n'est pas disponible.", 404)
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=path.name)

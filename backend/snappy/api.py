"""API REST de Snappy Transcript (sous /api) : réglages, périphériques, session live, exports, reprise après coup."""
from __future__ import annotations

import importlib.util
import sys
from typing import Any, Literal

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .audio.microphone import list_input_devices
from .audio.system_audio import list_output_devices
from .media import EXTENSIONS
from .service import ServiceError, StartParams, manager, new_upload
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
        "files": _present("av"),
        "file_extensions": list(EXTENSIONS),
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
        return {"ready": st.ready, "gpu_count": st.gpu_count, "detail": st.detail, "message": st.message}
    except Exception as exc:  # jamais d'erreur brute à l'écran : le processeur reste toujours possible
        from .transcription.cuda_runtime import CPU_SEUL
        return {"ready": False, "gpu_count": 0, "detail": f"Détection CUDA : {type(exc).__name__}: {exc}", "message": CPU_SEUL}


class CheminModele(BaseModel):
    path: str = ""


@router.get("/model")
def model() -> dict[str, Any]:
    """Modèle de l'équipe fourni par Studio Dock (null s'il n'y en a pas sur ce poste)."""
    from .service import team_model
    equipe = team_model()
    return {"team": None if equipe is None else {"name": equipe.name, "version": equipe.version, "path": equipe.path}}


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


class DemandeFichier(DemandeDemarrage):
    upload_id: str = ""  # fichier envoyé par le navigateur (POST /api/upload)
    path: str = ""       # ou chemin d'un fichier déjà sur ce PC (jamais modifié)


@router.post("/upload")
async def upload(request: Request, name: str = "") -> dict[str, Any]:
    """Reçoit le fichier brut dans le corps de la requête (sans formulaire) et l'écrit au fil de l'eau sur le disque."""
    upload_id, path = new_upload(name)
    size = 0
    try:
        with path.open("wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
                size += len(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".name").unlink(missing_ok=True)
        raise
    if size == 0:
        path.unlink(missing_ok=True)
        raise ServiceError("Le fichier est vide.", 422)
    return {"upload_id": upload_id, "size": size}


@router.post("/session/start-file")
def start_file(body: DemandeFichier) -> dict[str, Any]:
    champs = body.model_dump(exclude={"upload_id", "path"})
    return manager.start_file(StartParams(**champs), upload_id=body.upload_id, path=body.path)


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


@router.get("/session/level")
def level() -> dict[str, Any]:
    """Vu-mètre (appelé plusieurs fois par seconde pendant l'enregistrement) : niveau 0-1 et secondes de silence."""
    s = manager.current
    live = s.live if s else None
    if live is None or not hasattr(live, "level") or s.finished:
        return {"level": None, "silence": 0}
    return {"level": round(live.level, 3), "silence": round(live.silence_seconds, 1)}


class Correction(BaseModel):
    variant: Literal["raw", "diarized"] = "raw"
    index: int = Field(ge=0)
    text: str


@router.put("/session/segment")
def edit_segment(body: Correction) -> dict[str, Any]:
    if not manager.current:
        raise ServiceError("Aucune session.", 404)
    return manager.current.edit_segment(body.variant, body.index, body.text)


class Noms(BaseModel):
    names: dict[str, str]


@router.put("/session/speakers")
def rename_speakers(body: Noms) -> dict[str, Any]:
    if not manager.current:
        raise ServiceError("Aucune session.", 404)
    manager.current.rename_speakers(body.names)
    return {"speakers": manager.current.speakers()}


@router.post("/session/open-folder")
def open_current_folder() -> dict[str, bool]:
    manager.open_session_folder()
    return {"ok": True}


# --- Historique ----------------------------------------------------------------------------------------------

@router.get("/history")
def history() -> dict[str, Any]:
    return {"sessions": manager.history()}


@router.post("/history/{session_id}/open")
def reopen(session_id: str) -> dict[str, Any]:
    return manager.reopen(session_id)


@router.post("/history/{session_id}/folder")
def history_folder(session_id: str) -> dict[str, bool]:
    manager.open_session_folder(session_id)
    return {"ok": True}


@router.delete("/history/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    manager.delete_session(session_id)
    return {"sessions": manager.history()}


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

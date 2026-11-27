"""Serveur de l'app : l'API sous /api, /health pour Studio Dock, et l'interface compilée pour tout le reste."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import studiodock_ia
from app_info import APP_ID, APP_NAME, VERSION, dossier_interface
from snappy.api import router
from snappy.service import ServiceError, manager


@asynccontextmanager
async def cycle_de_vie(_: FastAPI):
    from snappy.diarization import prechauffer
    prechauffer()  # pyannote / PyTorch chargés en arrière-plan dès le démarrage
    yield
    manager.shutdown()  # referme proprement le WAV d'une session encore en cours


app = FastAPI(title=APP_NAME, version=VERSION, lifespan=cycle_de_vie)
app.include_router(router)


@app.exception_handler(ServiceError)
def erreur_utilisateur(_: Request, exc: ServiceError) -> JSONResponse:
    """Erreur attendue (champ invalide, session absente…) : message en français, lisible tel quel par l'interface."""
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


@app.get("/health")
def sante() -> dict[str, str]:
    """Contrat de Studio Dock : répond dès que le serveur tourne, avec l'identifiant de l'app."""
    return {"status": "ok", "app": APP_ID, "name": APP_NAME, "version": VERSION}


@app.get("/api/ia")
def ia() -> dict[str, object]:
    """Modèle d'IA réglé dans Studio Dock pour cette app (Réglages › Modèles d'IA), sans jamais renvoyer la clé."""
    choix = studiodock_ia.pour_app(APP_ID)
    if choix is None:
        return {"configure": False}
    return {"configure": True, "connexion": choix.connexion.name, "modele": choix.model, "local": choix.connexion.local}


# --- Interface compilée -------------------------------------------------------------------------------------

_INTERFACE = dossier_interface()
if (_INTERFACE / "index.html").is_file():
    if (_INTERFACE / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_INTERFACE / "assets"), name="assets")

    @app.get("/{chemin:path}", include_in_schema=False)
    def interface(chemin: str) -> FileResponse:
        fichier = (_INTERFACE / chemin).resolve()
        if chemin and fichier.is_file() and _INTERFACE.resolve() in fichier.parents:
            return FileResponse(fichier)
        return FileResponse(_INTERFACE / "index.html")

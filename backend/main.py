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


# --- Protection de l'API locale -----------------------------------------------------------------------------
# Le serveur n'écoute que sur 127.0.0.1, mais n'importe quelle page web ouverte dans le navigateur peut lui envoyer
# des requêtes. Trois garde-fous :
# 1. Host : seulement 127.0.0.1 / localhost (une page piégée qui fait pointer son propre domaine vers 127.0.0.1,
#    le « DNS rebinding », lirait sinon toutes les transcriptions) ;
# 2. requêtes qui modifient (POST, PUT, DELETE…) : seulement depuis l'interface de Snappy elle-même (en-tête Origin),
#    sinon un site pourrait lancer un enregistrement, effacer l'audio ou charger un faux modèle ;
# 3. en-têtes : pas d'affichage de Snappy dans une page tierce (clic piégé), pas de lecture de ses fichiers ailleurs.
HOTES_LOCAUX = {"127.0.0.1", "localhost", "::1"}
SURES = {"GET", "HEAD", "OPTIONS"}
ENTETES = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
}


def _nom_d_hote(valeur: str) -> str:
    from urllib.parse import urlsplit
    try:
        return (urlsplit(valeur if "://" in valeur else f"http://{valeur}").hostname or "").lower()
    except ValueError:
        return ""


@app.middleware("http")
async def garde_locale(request: Request, call_next):
    hote = request.headers.get("host", "")
    if _nom_d_hote(hote) not in HOTES_LOCAUX:
        return JSONResponse({"detail": "Adresse refusée : Snappy Transcript ne répond qu'à 127.0.0.1."}, status_code=403)
    if request.method not in SURES:
        origine = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site", "")
        if origine is not None and origine.rstrip("/").lower() not in {f"http://{hote}".lower(), f"https://{hote}".lower()}:
            return JSONResponse({"detail": "Requête refusée : elle ne vient pas de l'interface de Snappy Transcript."}, status_code=403)
        if origine is None and site in ("cross-site", "same-site"):
            return JSONResponse({"detail": "Requête refusée : elle ne vient pas de l'interface de Snappy Transcript."}, status_code=403)
    reponse = await call_next(request)
    for cle, valeur in ENTETES.items():
        reponse.headers.setdefault(cle, valeur)
    return reponse


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

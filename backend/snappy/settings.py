"""Réglages mémorisés d'une session à l'autre, dans <dossier de données>/settings.json (écriture atomique)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .paths import app_data_dir

DEFAULTS: dict[str, Any] = {
    "mode": "live",                  # live (micro / son du PC) | file (fichier audio ou vidéo)
    "source": "mixed",               # microphone | system | mixed (défaut : ma voix + une application)
    "engine": "local",               # local | mock
    "input_device": "",              # nom du micro ; vide : le premier détecté
    "output_device": "",             # nom de la sortie Windows à capturer ; vide : la sortie par défaut
    "ecoute": "voix_app",            # choix « On écoute » : voix | app | tout | voix_app | voix_tout
    "app": "",                       # programme dont on capte le son seul (« ms-teams.exe ») ; vide : tout le son
    "app_name": "",                  # son nom lisible (« Microsoft Teams »), pour les messages quand elle est fermée
    "model_path": "",                # modèle choisi sur ce poste (seulement si use_own_model)
    "use_own_model": False,          # False : modèle de l'équipe, fourni par Studio Dock
    "acceleration": "auto",          # auto | gpu | cpu
    "language": "auto",              # auto | fr | en
    "glossary": "",
    "chunk_seconds": 5,
    "overlap_seconds": 0.75,
    "vad_filter": True,
    "save_audio": True,
    "diarization": True,
    "diarization_model_path": "",
    "use_own_diarization_model": False, # True : dossier indiqué ici plutôt que le modèle de l'équipe (Studio Dock)
    "speaker_hint": 0,
}

_LOCK = threading.RLock()


def settings_file() -> Path:
    return app_data_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    """Réglages enregistrés complétés par les valeurs par défaut ; un fichier illisible redonne les défauts."""
    saved: dict[str, Any] = {}
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            saved = {k: v for k, v in data.items() if k in DEFAULTS and type(v) is type(DEFAULTS[k])}
    except (OSError, ValueError):
        pass
    return {**DEFAULTS, **saved}


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Enregistre les clés connues dont le type est correct (les autres sont ignorées) et renvoie l'ensemble."""
    with _LOCK:
        current = load_settings()
        for key, value in values.items():
            if key in DEFAULTS and (type(value) is type(DEFAULTS[key])
                                    or (isinstance(DEFAULTS[key], float) and type(value) is int)):
                current[key] = float(value) if isinstance(DEFAULTS[key], float) else value
        target = settings_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".tmp", prefix="settings_",
                                             dir=target.parent, delete=False) as tmp:
                tmp_name = tmp.name
                json.dump(current, tmp, ensure_ascii=False, indent=2)
            os.replace(tmp_name, target)
        finally:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)
        return current

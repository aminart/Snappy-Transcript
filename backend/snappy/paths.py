"""Dossier de données de l'application (réglages, sessions, copie de récupération), selon le système."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """SNAPPY_DATA si défini ; sinon %LOCALAPPDATA% (Windows), ~/Library/Application Support (Mac) ou
    ~/.local/share (Linux), dans un dossier « SnappyTranscript »."""
    if override := os.environ.get("SNAPPY_DATA", "").strip():
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "SnappyTranscript"

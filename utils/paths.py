"""Dossier de données de l'application (sessions, cache de récupération), selon le système."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """AUDIO_TRANSCRIBER_DATA si défini ; sinon %LOCALAPPDATA% (Windows), ~/Library/Application Support (Mac),
    ~/.local/share (Linux), sous un dossier « AudioTranscriber »."""
    if override := os.environ.get("AUDIO_TRANSCRIBER_DATA", "").strip():
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "AudioTranscriber"

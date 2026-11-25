import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def donnees_isolees(tmp_path, monkeypatch):
    """Sessions, cache et réglages écrits dans un dossier temporaire, jamais dans le profil de l'utilisateur."""
    monkeypatch.setenv("AUDIO_TRANSCRIBER_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("AUDIO_TRANSCRIBER_SETTINGS", str(tmp_path / "settings"))

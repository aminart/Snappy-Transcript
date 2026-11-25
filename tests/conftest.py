import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def donnees_isolees(tmp_path, monkeypatch):
    """Sessions, cache et réglages écrits dans un dossier temporaire, jamais dans le profil de l'utilisateur."""
    monkeypatch.setenv("SNAPPY_DATA", str(tmp_path / "data"))
    from snappy.service import PosthocJob, manager
    manager.current, manager.posthoc = None, PosthocJob()
    yield
    manager.current = None

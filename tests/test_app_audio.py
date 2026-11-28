"""Son d'une seule application : regroupement par application, conversion du son, choix au démarrage.

La capture Windows elle-même (WASAPI) ne tourne que sur un vrai poste ; ici on remplace le module _wasapi par un
double pour vérifier tout ce qui l'entoure (fil de capture, découpage en blocs, erreurs remontées).
"""
import sys
import time
import types

import numpy as np
import pytest
from fakes import SourceContinue
from fastapi.testclient import TestClient

from main import app
from snappy.audio import app_audio
from snappy.audio.app_audio import AppAudio, ProcessLoopbackSource, choisir, recommandee, regrouper, vers_mono
from snappy.audio.system_audio import MixedAudioSource
from snappy.service import ServiceError, StartParams, manager

# Arbre de processus fictif : pid → (parent, programme)
ARBRE = {
    1: (0, "wininit.exe"), 10: (1, "explorer.exe"), 11: (1, "svchost.exe"),
    100: (10, "ms-teams.exe"), 101: (100, "msedgewebview2.exe"), 102: (101, "msedgewebview2.exe"),
    200: (10, "chrome.exe"), 201: (200, "chrome.exe"), 202: (200, "chrome.exe"),
    300: (11, "Zoom.exe"),
    400: (10, "python.exe"), 401: (400, "snappy.exe"),
    500: (10, "outil-maison.exe"),
}
parent = lambda pid: ARBRE[pid][0] if pid in ARBRE else None  # noqa: E731
exe_de = lambda pid: ARBRE[pid][1] if pid in ARBRE else None  # noqa: E731


def test_les_sessions_sont_regroupees_par_application_racine():
    sessions = [
        (0, True, 0.5),          # « Sons système » : ignoré
        (102, True, 0.30),       # Teams joue dans un sous-processus WebView
        (201, True, 0.10), (202, False, 0.0),  # deux onglets Chrome
        (300, False, 0.0),       # Zoom ouvert mais silencieux
        (401, True, 0.9),        # Snappy lui-même : exclu
        (500, True, 0.0001),     # session active mais silencieuse
        (999, True, 0.4),        # processus disparu entre-temps
    ]
    apps = regrouper(sessions, parent, exe_de, exclus={400})
    assert [(a.exe, a.pid) for a in apps] == [("ms-teams.exe", 100), ("chrome.exe", 200), ("outil-maison.exe", 500), ("zoom.exe", 300)]
    teams, chrome, maison, zoom = apps
    assert teams.name == "Microsoft Teams" and teams.active and teams.visio and teams.level == pytest.approx(0.30)
    assert chrome.name == "Google Chrome" and chrome.active and not chrome.visio
    assert not maison.active and maison.name == "Outil Maison"  # sous le seuil : ne « fait pas de son »
    assert not zoom.active and zoom.visio
    assert recommandee(apps) is teams
    assert choisir(apps, "MS-Teams.exe ") is teams and choisir(apps, "spotify.exe") is None


def test_la_description_du_programme_sert_de_nom():
    apps = regrouper([(500, True, 0.2)], parent, exe_de, description_de=lambda pid: "Outil de visio maison")
    assert apps[0].name == "Outil de visio maison"


def test_recommandation_une_visio_ouverte_meme_silencieuse():
    zoom = AppAudio("zoom.exe", "Zoom", 3, False, 0.0, True)
    chrome = AppAudio("chrome.exe", "Google Chrome", 2, True, 0.2, False)
    assert recommandee([chrome, zoom]) is zoom
    assert recommandee([chrome]) is None


def test_conversion_en_mono_16_khz():
    t = np.arange(48000) / 48000
    gauche = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    stereo = np.stack([gauche, gauche], axis=1).reshape(-1)
    mono = vers_mono(stereo, 2, 48000)
    assert mono.dtype == np.int16 and len(mono) == 16000
    assert abs(np.abs(mono).max() - 10000) < 300  # l'amplitude est conservée
    assert len(vers_mono(np.zeros(44100 * 2, np.int16), 2, 44100)) == 16000
    deja = np.arange(1600, dtype=np.int16)
    assert np.array_equal(vers_mono(deja, 1, 16000), deja)


def test_hors_windows_la_fonction_est_annoncee_indisponible():
    if sys.platform == "win32":
        pytest.skip("vérifié sur un poste non Windows")
    ok, raison = app_audio.app_capture_status()
    assert not ok and "Windows" in raison
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.get("/api/audio-apps").json()
        assert r == {"supported": False, "reason": raison, "apps": [], "recommended": ""}
        assert c.get("/api/capabilities").json()["app_audio"] is False


# --- Capture : fil, blocs et erreurs, avec un faux WASAPI ---------------------------------------------------

class _FausseCapture:
    """48 kHz stéréo, 20 ms par paquet, comme le format de repli."""
    taux, canaux = 48000, 2

    def __init__(self, pid):
        if pid == 666:
            raise OSError("E_ACCESSDENIED")
        self.n = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def lire(self, attente_ms):
        time.sleep(0.005)
        self.n += 1
        return [(np.ones(960 * 2, np.int16) * 1000).tobytes()]


@pytest.fixture
def faux_wasapi(monkeypatch):
    import contextlib
    module = types.SimpleNamespace(com_mta=contextlib.nullcontext, CaptureProcessus=_FausseCapture)
    monkeypatch.setitem(sys.modules, "snappy.audio._wasapi", module)
    import snappy.audio
    monkeypatch.setattr(snappy.audio, "_wasapi", module, raising=False)
    return module


def test_capture_d_une_application_en_blocs_de_100_ms(faux_wasapi):
    src = ProcessLoopbackSource(100, "Microsoft Teams")
    src.start()
    try:
        bloc = None
        fin = time.monotonic() + 3
        while bloc is None and time.monotonic() < fin:
            bloc = src.read_chunk(0.2)
        assert bloc is not None and len(bloc) == 1600 * 2  # 100 ms en PCM16 mono 16 kHz
        assert set(np.frombuffer(bloc, np.int16)) == {1000}
    finally:
        src.stop()


def test_refus_de_windows_remonte_au_demarrage(faux_wasapi):
    src = ProcessLoopbackSource(666, "Microsoft Teams")
    with pytest.raises(OSError, match="Windows refuse de capter le son de Microsoft Teams"):
        src.start()


def test_micro_referme_si_l_application_est_refusee(faux_wasapi):
    micro = SourceContinue()
    mix = MixedAudioSource(micro, ProcessLoopbackSource(666, "Zoom"))
    with pytest.raises(OSError):
        mix.start()
    assert micro.arretee


# --- Démarrage d'une session ---------------------------------------------------------------------------------

def test_demarrage_application_non_ouverte(monkeypatch):
    monkeypatch.setattr(app_audio, "app_capture_status", lambda: (True, ""))
    monkeypatch.setattr(app_audio, "list_audio_apps", lambda: [AppAudio("chrome.exe", "Google Chrome", 2, True, 0.2, False)])
    with pytest.raises(ServiceError, match="Microsoft Teams n'est pas ouvert") as e:
        manager._source(StartParams(source="system", app="ms-teams.exe"))
    assert e.value.status == 422


def test_demarrage_windows_trop_ancien(monkeypatch):
    monkeypatch.setattr(app_audio, "app_capture_status", lambda: (False, "trop ancien"))
    with pytest.raises(ServiceError, match="trop ancien"):
        manager._source(StartParams(source="mixed", input_device=0, app="zoom.exe"))


def test_demarrage_avec_l_application_choisie(monkeypatch, faux_wasapi):
    monkeypatch.setattr(app_audio, "app_capture_status", lambda: (True, ""))
    monkeypatch.setattr(app_audio, "list_audio_apps", lambda: [AppAudio("ms-teams.exe", "Microsoft Teams", 100, True, 0.3, True)])
    src = manager._source(StartParams(source="system", app="ms-teams.exe"))
    assert isinstance(src, ProcessLoopbackSource) and src.pid == 100 and src.name == "Microsoft Teams"
    with TestClient(app, base_url="http://127.0.0.1") as c:
        demarrage = {"engine": "mock", "source": "system", "app": "ms-teams.exe", "chunk_seconds": 3, "diarization": False}
        etat = c.post("/api/session/start", json=demarrage).json()
        assert etat["active"]
        fin = time.monotonic() + 8
        while c.get("/api/session").json()["duration"] < 0.5 and time.monotonic() < fin:
            time.sleep(0.05)
        c.post("/api/session/stop")
        while not c.get("/api/session").json()["finalized"] and time.monotonic() < fin + 8:
            time.sleep(0.05)
        assert c.delete("/api/session").json() == {"ok": True}

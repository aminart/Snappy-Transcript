"""Détection du GPU : jamais d'erreur brute, et le processeur reste toujours possible."""
import importlib.util

from fastapi.testclient import TestClient

from main import app
from snappy.transcription import cuda_runtime


def test_sans_paquets_nvidia_pas_d_exception(monkeypatch):
    """Régression : find_spec("nvidia") renvoie None sur un PC sans GPU, et la détection levait AttributeError
    (ce qui empêchait aussi le moteur réel de démarrer en mode « Automatique »)."""
    vrai = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda nom, *a: None if nom == "nvidia" else vrai(nom, *a))
    etat = cuda_runtime.prepare_cuda_runtime()
    assert etat.ready is False and "processeur" in etat.message


def test_l_api_renvoie_un_message_lisible(monkeypatch):
    def panne():
        raise AttributeError("'NoneType' object has no attribute 'x'")
    monkeypatch.setattr(cuda_runtime, "prepare_cuda_runtime", panne)
    r = TestClient(app, base_url="http://127.0.0.1").get("/api/cuda").json()
    assert r["ready"] is False and "processeur" in r["message"] and "NoneType" not in r["message"]

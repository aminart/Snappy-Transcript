"""Transcription d'un fichier de bout en bout par l'API, avec le moteur de simulation."""
import time

import pytest
from fastapi.testclient import TestClient
from medias import ecrire, video_sans_son

from main import app
from snappy.models import TranscriptSegment
from snappy.service import manager, uploads_dir
from snappy.transcription.mock import MockProvider

OPTIONS = {"engine": "mock", "diarization": False}


@pytest.fixture
def client():
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def attendre(client, condition, delai=15.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        etat = client.get("/api/session").json()
        if condition(etat):
            return etat
        time.sleep(0.05)
    raise AssertionError(f"délai dépassé : {etat}")


def envoyer(client, chemin):
    r = client.post("/api/upload", params={"name": chemin.name}, content=chemin.read_bytes())
    assert r.status_code == 200, r.text
    return r.json()["upload_id"]


def test_video_envoyee_par_le_navigateur(client, tmp_path):
    video = ecrire(tmp_path / "réunion équipe.mp4", "aac", secondes=12, video=True)
    upload_id = envoyer(client, video)
    assert upload_id.endswith(".mp4") and (uploads_dir() / upload_id).is_file()

    etat = client.post("/api/session/start-file", json={**OPTIONS, "upload_id": upload_id}).json()
    assert etat["kind"] == "file" and etat["file"]["name"] == "réunion équipe.mp4"
    fin = attendre(client, lambda e: e["finalized"])

    assert fin["status"] == "STOPPED" and not fin["error"]
    assert fin["duration"] == pytest.approx(12, abs=0.2) and fin["file"]["fraction"] == 1
    assert fin["total"] == 3  # simulation : un segment par morceau de 5 s
    assert all(fin["files"][k] for k in ("wav", "raw_txt", "raw_srt"))
    assert "MODE TEST" in client.get("/api/session/file/raw_txt").text
    # la copie envoyée est supprimée une fois lue ; le WAV 16 kHz reste pour le lecteur
    assert not any(uploads_dir().iterdir())
    assert client.get("/api/session/file/wav", headers={"Range": "bytes=0-43"}).status_code == 206


def test_fichier_deja_sur_le_pc_jamais_modifie(client, tmp_path):
    audio = ecrire(tmp_path / "interview.m4a", "aac", secondes=6)
    avant = audio.read_bytes()
    client.post("/api/session/start-file", json={**OPTIONS, "path": f'"{audio}"'})
    fin = attendre(client, lambda e: e["finalized"])
    assert fin["total"] == 2 and audio.read_bytes() == avant


def test_fichier_illisible_message_clair(client, tmp_path):
    muet = video_sans_son(tmp_path / "muet.mp4")
    client.post("/api/session/start-file", json={**OPTIONS, "path": str(muet), "diarization": True,
                                                  "diarization_model_path": "x"})
    fin = attendre(client, lambda e: e["finalized"])
    assert fin["status"] == "ERROR" and "aucune piste audio" in fin["error"]
    assert fin["diarization"]["status"] == "IDLE"


def test_erreurs_avant_le_depart(client, tmp_path):
    assert client.post("/api/session/start-file", json=OPTIONS).status_code == 422
    assert client.post("/api/session/start-file", json={**OPTIONS, "path": str(tmp_path / "absent.mp3")}).status_code == 422
    assert client.post("/api/session/start-file", json={**OPTIONS, "upload_id": "../../etc/passwd"}).status_code == 404
    assert client.post("/api/session/start-file", json={**OPTIONS, "upload_id": "a" * 24 + ".mp3"}).status_code == 404
    assert client.post("/api/upload", params={"name": "vide.mp3"}, content=b"").status_code == 422


class Lent(MockProvider):
    def transcribe(self, pcm, sample_rate, offset, language):
        time.sleep(0.3)
        return super().transcribe(pcm, sample_rate, offset, language)


def test_pause_puis_arret_garde_le_texte_deja_transcrit(client, tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "_provider", lambda p: Lent())
    audio = ecrire(tmp_path / "long.flac", "flac", secondes=60)
    client.post("/api/session/start-file", json={**OPTIONS, "path": str(audio)})
    attendre(client, lambda e: e["total"] >= 1)

    assert client.post("/api/session/pause").json()["paused"] is True
    en_pause = attendre(client, lambda e: e["status"] == "PAUSED")
    time.sleep(0.8)
    assert client.get("/api/session").json()["total"] <= en_pause["total"] + 1  # plus rien n'avance

    client.post("/api/session/resume")
    client.post("/api/session/stop")
    fin = attendre(client, lambda e: e["finalized"])
    assert fin["status"] == "STOPPED" and 1 <= fin["total"] < 12
    assert fin["files"]["raw_txt"]


def test_diarisation_apres_un_fichier(client, tmp_path, monkeypatch):
    monkeypatch.setattr("snappy.service._diarize", lambda wav, segs, m, n, job: [
        TranscriptSegment(s.start, s.end, s.text, "SPEAKER_00") for s in segs()])
    monkeypatch.setattr("snappy.service._validate_pipeline", lambda path: "ok")
    monkeypatch.setattr("snappy.diarization.validate_diarization_model", lambda path: (True, "ok"))
    audio = ecrire(tmp_path / "a.mp3", "libmp3lame", secondes=6)
    client.post("/api/session/start-file", json={**OPTIONS, "path": str(audio), "diarization": True,
                                                  "diarization_model_path": "x"})
    fin = attendre(client, lambda e: e["diarization"]["status"] == "DONE")
    assert "SPEAKER_00" in client.get("/api/session/file/diarized_txt").text and fin["kind"] == "file"


def test_capacites_annoncent_les_fichiers(client):
    cap = client.get("/api/capabilities").json()
    assert cap["files"] is True and ".mp4" in cap["file_extensions"] and ".mp3" in cap["file_extensions"]

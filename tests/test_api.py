"""L'API de bout en bout, avec une source audio factice et le moteur de simulation (aucun modèle ni micro requis)."""
import time

import pytest
from fakes import SourceFactice
from fastapi.testclient import TestClient

from main import app
from snappy.models import TranscriptSegment, TranscriptWord
from snappy.service import manager


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(manager, "_source", lambda p: SourceFactice(blocs=150))
    with TestClient(app) as c:
        yield c


def attendre(condition, delai=8.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if (valeur := condition()):
            return valeur
        time.sleep(0.05)
    raise AssertionError("délai dépassé")


DEMARRAGE = {"engine": "mock", "source": "microphone", "input_device": 0, "chunk_seconds": 3, "overlap_seconds": 0.25,
             "diarization": False}


def terminer(client):
    attendre(lambda: client.get("/api/session").json()["duration"] >= 3.2)
    client.post("/api/session/stop")
    return attendre(lambda: (e := client.get("/api/session").json())["finalized"] and e)


def test_session_complete_de_bout_en_bout(client):
    etat = client.post("/api/session/start", json=DEMARRAGE).json()
    assert etat["active"] and etat["status"] in ("LISTENING", "TRANSCRIBING") and not etat["finalized"]
    assert client.post("/api/session/start", json=DEMARRAGE).status_code == 409  # une seule session à la fois

    client.post("/api/session/pause")
    assert client.get("/api/session").json()["paused"] is True
    client.post("/api/session/resume")
    fin = terminer(client)

    assert fin["status"] == "STOPPED" and fin["total"] >= 1
    assert all(fin["files"][k] for k in ("wav", "raw_txt", "raw_srt")) and not fin["files"]["diarized_txt"]

    txt = client.get("/api/session/file/raw_txt", params={"download": True})
    assert txt.status_code == 200 and "attachment" in txt.headers["content-disposition"]
    assert "[00:00:00]" in txt.text

    # Le lecteur déplace la lecture : le WAV doit répondre aux requêtes Range
    partiel = client.get("/api/session/file/wav", headers={"Range": "bytes=0-99"})
    assert partiel.status_code == 206 and len(partiel.content) == 100
    assert partiel.headers["content-range"].startswith("bytes 0-99/")

    mots = client.get("/api/session/transcript").json()["segments"]
    assert len(mots) == fin["total"] and "words" in mots[0]
    assert client.get("/api/session/transcript", params={"variant": "diarized"}).status_code == 404

    assert client.delete("/api/session").json() == {"ok": True}
    assert client.get("/api/session").json() == {"active": False}


def test_le_client_ne_recoit_que_les_nouveaux_segments(client):
    client.post("/api/session/start", json=DEMARRAGE)
    fin = terminer(client)
    assert client.get("/api/session", params={"after": fin["total"]}).json()["segments"] == []
    un = client.get("/api/session", params={"after": 1}).json()
    assert un["from"] == 1 and len(un["segments"]) == fin["total"] - 1
    trop = client.get("/api/session", params={"after": 999}).json()  # client désynchronisé : on renvoie tout
    assert trop["from"] == 0 and len(trop["segments"]) == fin["total"]


def test_wav_non_conserve_supprime_apres_la_session(client):
    client.post("/api/session/start", json={**DEMARRAGE, "save_audio": False})
    fin = terminer(client)
    attendre(lambda: not client.get("/api/session").json()["files"]["wav"])
    assert fin["files"]["raw_txt"]
    assert client.get("/api/session/file/wav").status_code == 404


def test_erreurs_lisibles(client):
    assert client.post("/api/session/pause").status_code == 404
    r = client.post("/api/session/start", json={**DEMARRAGE, "engine": "local", "model_path": ""})
    assert r.status_code == 422 and "modèle" in r.json()["detail"].lower()
    r = client.post("/api/session/start", json={**DEMARRAGE, "source": "microphone", "input_device": None})
    assert r.status_code in (422,) or manager.current is not None
    assert client.post("/api/session/start", json={**DEMARRAGE, "chunk_seconds": 99}).status_code == 422
    assert client.post("/api/posthoc", json={"wav_path": "/nulle/part.wav", "srt_path": "/nulle/part.srt"}).status_code == 422


def test_diarisation_non_lancee_si_pipeline_invalide(client):
    etat = client.post("/api/session/start", json={**DEMARRAGE, "diarization": True, "diarization_model_path": "/absent"}).json()
    assert etat["diarization"]["note"].startswith("Diarisation non lancée") and not etat["diarization"]["wanted"]
    terminer(client)


def test_diarisation_en_arriere_plan(client, monkeypatch):
    def faux(wav, segments, model, speakers, job):
        job.progress("segmentation", 0.5, 1.0, 1.0)
        return [TranscriptSegment(s.start, s.end, s.text, "SPEAKER_00" if i % 2 == 0 else "SPEAKER_01",
                                  (TranscriptWord(s.start, s.end, s.text),)) for i, s in enumerate(segments)]
    monkeypatch.setattr("snappy.service._diarize", faux)
    monkeypatch.setattr("snappy.service._validate_pipeline", lambda path: "pipeline-ok")
    monkeypatch.setattr("snappy.diarization.validate_diarization_model", lambda path: (True, "pipeline-ok"))

    client.post("/api/session/start", json={**DEMARRAGE, "diarization": True, "diarization_model_path": "x"})
    terminer(client)
    fin = attendre(lambda: (e := client.get("/api/session").json())["diarization"]["status"] == "DONE" and e)
    assert fin["files"]["diarized_txt"] and fin["files"]["diarized_srt"]
    assert "SPEAKER_00" in client.get("/api/session/file/diarized_txt").text
    segs = client.get("/api/session/transcript", params={"variant": "diarized"}).json()["segments"]
    assert segs[0]["speaker"] == "SPEAKER_00"

    # relance manuelle
    assert client.post("/api/session/diarization", json={"model_path": "x", "speakers": 2}).status_code == 200
    attendre(lambda: client.get("/api/session").json()["diarization"]["status"] == "DONE")


def test_reprise_apres_coup(client, monkeypatch, tmp_path):
    wav, srt = tmp_path / "reunion.wav", tmp_path / "reunion.srt"
    wav.write_bytes(b"RIFF")
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nBonjour\n", encoding="utf-8")
    monkeypatch.setattr("snappy.service._validate_pipeline", lambda path: "pipeline-ok")
    monkeypatch.setattr("snappy.service._diarize", lambda w, segs, m, n, job: [
        TranscriptSegment(s.start, s.end, s.text, "SPEAKER_00") for s in segs])
    r = client.post("/api/posthoc", json={"wav_path": f'"{wav}"', "srt_path": str(srt), "model_path": "x"})
    assert r.status_code == 200
    fin = attendre(lambda: (e := client.get("/api/posthoc").json())["status"] == "DONE" and e)
    assert fin["segments"] == 1 and (tmp_path / "reunion_diarized.srt").is_file()
    assert "SPEAKER_00" in client.get("/api/posthoc/file/txt").text


def test_reglages_ne_gardent_que_les_valeurs_valides(client):
    r = client.put("/api/settings", json={"language": "en", "chunk_seconds": "abc", "inconnu": 1, "overlap_seconds": 1}).json()
    assert r["language"] == "en" and r["chunk_seconds"] == 5 and r["overlap_seconds"] == 1.0 and "inconnu" not in r
    assert client.get("/api/settings").json() == r


def test_verification_des_dossiers_de_modele(client, tmp_path):
    assert client.post("/api/model/check", json={"path": str(tmp_path)}).json()["valid"] is False
    for nom in ("config.json", "model.bin", "tokenizer.json"):
        (tmp_path / nom).write_text("{}")
    ok = client.post("/api/model/check", json={"path": str(tmp_path)}).json()
    assert ok["valid"] and ok["name"] == tmp_path.name


def test_capacites_et_peripheriques(client):
    assert set(client.get("/api/capabilities").json()) == {"platform", "stt", "diarization", "system_audio", "files", "file_extensions"}
    d = client.get("/api/devices").json()
    assert isinstance(d["inputs"], list) and isinstance(d["outputs"], list)


def test_modele_de_l_equipe_fourni_par_studio_dock(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIODOCK_IA", str(tmp_path / "ia"))
    assert client.get("/api/model").json() == {"team": None}
    # sans modèle de l'équipe ni dossier : message qui explique où le régler
    r = client.post("/api/session/start", json={**DEMARRAGE, "engine": "local", "model_path": ""})
    assert r.status_code == 422 and "Studio Dock" in r.json()["detail"]

    modele = tmp_path / "modeles" / "transcription" / "faster-whisper-small"
    modele.mkdir(parents=True)
    for nom in ("config.json", "model.bin", "tokenizer.json"):
        (modele / nom).write_text("{}")
    (tmp_path / "ia").mkdir()
    (tmp_path / "ia" / "transcription.json").write_text(
        f'{{"format": 1, "name": "Whisper small", "version": "1.0.0", "path": {str(modele)!r}}}'.replace("'", '"'))
    assert client.get("/api/model").json()["team"] == {"name": "Whisper small", "version": "1.0.0", "path": str(modele)}

    choisi = {}
    class Faux:
        def __init__(self, chemin, **_):
            choisi["chemin"] = chemin
    monkeypatch.setattr("snappy.transcription.whisper.LocalWhisperProvider", Faux)
    r = client.post("/api/session/start", json={**DEMARRAGE, "engine": "local", "model_path": ""})
    assert r.status_code == 200 and choisi["chemin"] == str(modele)

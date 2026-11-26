"""Fonctions issues de la maquette : test de la source, moments marqués, titre, remplacer partout, export Word,
forme d'onde, recherche dans « Mes transcriptions » et récupération d'une session interrompue."""
import json
import time
import zipfile
from io import BytesIO
from xml.etree import ElementTree

import numpy as np
from fakes import BLOC, SourceContinue
from test_exploitation import DEMARRAGE, attendre, client, session_terminee  # noqa: F401 (fixture)

from snappy.documents import extrait, lire_copie, motif, remplacer, sans_accents
from snappy.paths import app_data_dir
from snappy.service import manager, sessions_dir

SON = (np.sin(np.arange(1600) / 5) * 8000).astype(np.int16).tobytes()


class SourceSon(SourceContinue):
    def read_chunk(self, timeout=0.2):
        time.sleep(0.01)
        return None if self.arretee else SON


# --- test de la source avant de démarrer ---------------------------------------------------------------------

def test_apercu_entend_la_voix_puis_se_ferme_au_demarrage(client, monkeypatch):
    ouvertes = []

    def sources(p):
        s = {"voix": SourceSon(), "autre": SourceContinue()}
        ouvertes.append(s)
        return s
    monkeypatch.setattr(manager, "_sources", sources)
    e = client.post("/api/preview", json=DEMARRAGE).json()
    assert e["active"]
    fin = time.monotonic() + 3
    while not (e := client.get("/api/preview").json())["voix"]["heard"] and time.monotonic() < fin:
        time.sleep(0.05)
    assert e["voix"]["heard"] and e["voix"]["level"] > 0.5
    assert not e["autre"]["heard"] and e["autre"]["level"] == 0  # silence numérique : rien n'est capté
    client.post("/api/preview", json=DEMARRAGE)  # mêmes réglages : rien n'est rouvert
    assert len(ouvertes) == 1
    client.post("/api/session/start", json=DEMARRAGE)  # démarrer referme l'aperçu (micro libéré)
    assert client.get("/api/preview").json() == {"active": False}
    assert all(s.arretee for s in ouvertes[0].values())
    assert client.post("/api/preview", json=DEMARRAGE).status_code == 409  # pas pendant une session
    client.post("/api/session/stop")


# --- moments marqués et titre ---------------------------------------------------------------------------------

def test_moments_marques_titre_et_reouverture(client):
    client.post("/api/session/start", json=DEMARRAGE)
    attendre(client, lambda e: e["total"] >= 1)
    m = client.post("/api/session/marks").json()["marks"]
    assert len(m) == 1 and m[0]["t"] > 0 and not m[0]["named"] and m[0]["label"].startswith("[MODE TEST")
    assert len(client.post("/api/session/marks").json()["marks"]) == 1  # double appui sur M ignoré
    attendre(client, lambda e: e["duration"] >= m[0]["t"] + 2.5)
    client.post("/api/session/marks", json={"label": "Décision budget"})
    client.post("/api/session/stop")
    fin = attendre(client, lambda e: e["finalized"])
    assert [x["label"] for x in fin["marks"]][1] == "Décision budget"
    assert client.post("/api/session/marks").status_code == 409  # plus après l'arrêt

    assert client.put("/api/session/marks/0", json={"label": "Lancement confirmé"}).json()["marks"][0]["named"]
    assert len(client.put("/api/session/marks/1", json={"label": None}).json()["marks"]) == 1
    assert client.put("/api/session/title", json={"title": "  Comité   projet  "}).json() == {"title": "Comité projet"}
    assert fin["default_title"].startswith("Enregistrement du ")

    sid = fin["id"]
    fiche = json.loads((sessions_dir() / sid / "session.json").read_text(encoding="utf-8"))
    assert fiche["title"] == "Comité projet" and fiche["marks"][0]["label"] == "Lancement confirmé"
    client.delete("/api/session")
    h = client.get("/api/history").json()["sessions"][0]
    assert h["title"] == "Comité projet" and h["marks"] == 1 and h["excerpt"]["after"].startswith("[MODE TEST")
    assert client.put(f"/api/history/{sid}/title", json={"title": "Comité budget"}).json() == {"title": "Comité budget"}
    e = client.post(f"/api/history/{sid}/open").json()
    assert e["title"] == "Comité budget" and e["marks"] == [{"t": fiche["marks"][0]["t"], "label": "Lancement confirmé", "named": True}]


# --- rechercher / remplacer -----------------------------------------------------------------------------------

def test_motif_mot_entier_et_majuscules():
    assert remplacer("Tracelaine, tracelaine et Tracelaines", motif("tracelaine", mot_entier=True), "Traceline") == \
        ("Traceline, Traceline et Tracelaines", 2)
    assert remplacer("Tracelaine tracelaine", motif("tracelaine", casse=True), "X") == ("Tracelaine X", 1)
    assert remplacer("1+1 (a)", motif("(a)"), "b") == ("1+1 b", 1)  # caractères spéciaux pris tels quels


def test_tout_remplacer_puis_annuler(client, monkeypatch):
    fin = session_terminee(client, diariser=True, monkeypatch=monkeypatch)
    avant = client.get("/api/session/transcript").json()["segments"]
    r = client.post("/api/session/replace", json={"find": "mode test", "replace": "Essai", "whole_word": True}).json()
    assert r["replaced"] == len(avant) >= 2
    apres = client.get("/api/session/transcript").json()["segments"]
    assert all(s["text"].startswith("[Essai —") for s in apres)
    assert all("Essai" in s["text"] for s in client.get("/api/session/transcript", params={"variant": "diarized"}).json()["segments"])
    assert "Essai" in client.get("/api/session/file/raw_txt").text  # les exports suivent
    assert client.get("/api/session").json()["can_undo"]
    client.post("/api/session/replace/undo")
    assert client.get("/api/session/transcript").json()["segments"][0]["text"] == avant[0]["text"]
    assert client.post("/api/session/replace/undo").status_code == 409
    assert client.post("/api/session/replace", json={"find": "introuvable", "replace": "x"}).json() == {"replaced": 0}
    assert fin["finalized"]


# --- export Word et forme d'onde -------------------------------------------------------------------------------

def test_export_word(client, monkeypatch):
    session_terminee(client, diariser=True, monkeypatch=monkeypatch)
    client.put("/api/session/speakers", json={"names": {"SPEAKER_00": "Marie"}})
    client.put("/api/session/title", json={"title": "Comité : budget/2026"})
    r = client.get("/api/session/docx")
    assert r.status_code == 200 and "Comit%C3%A9%20-%20budget-2026.docx" in r.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(r.content)) as z:
        assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml"} <= set(z.namelist())
        doc = z.read("word/document.xml").decode()
    ElementTree.fromstring(doc)  # XML bien formé
    assert "Comité : budget/2026" in doc and "Marie : " in doc and "SPEAKER_01 : " in doc


def test_forme_d_onde(client):
    session_terminee(client)
    o = client.get("/api/session/waveform", params={"n": 100}).json()
    assert len(o["peaks"]) == 100 and o["duration"] >= 7 and all(0 <= p <= 1 for p in o["peaks"])


# --- « Mes transcriptions » : recherche et récupération --------------------------------------------------------

def test_extrait_sans_accents():
    assert sans_accents("Été À") == "ete a" and len(sans_accents("Été")) == 3
    e = extrait("On valide le report de 15 000 € sur janvier, et Marie prépare le planning.", "REPORT")
    assert e == {"before": "On valide le ", "match": "report", "after": " de 15 000 € sur janvier, et Marie prépare le planning."}
    assert extrait("abc", "zzz") is None


def test_recherche_dans_mes_transcriptions(client):
    session_terminee(client)
    client.put("/api/session/title", json={"title": "Réunion"})
    client.delete("/api/session")
    assert len(client.get("/api/history", params={"q": "fenetre"}).json()["sessions"]) == 1  # « fenêtre » sans accent
    assert len(client.get("/api/history", params={"q": "réunion"}).json()["sessions"]) == 1   # le titre compte
    assert client.get("/api/history", params={"q": "introuvable"}).json()["sessions"] == []
    h = client.get("/api/history", params={"q": "mode test"}).json()["sessions"][0]
    assert h["excerpt"]["match"] == "MODE TEST" and h["matches"] >= 2


def test_recuperer_une_session_interrompue(client):
    sid = "2026-01-02_03-04-05"
    d = sessions_dir() / sid
    d.mkdir(parents=True)
    (app_data_dir() / "cache").mkdir(parents=True, exist_ok=True)
    (app_data_dir() / "cache" / f"transcript_{sid}.txt").write_text(
        "[00:00:01] Bonjour à tous.\n[00:00:06] On commence par le budget.\n", encoding="utf-8")
    h = client.get("/api/history").json()["sessions"][0]
    assert h["interrupted"] and h["recoverable"] and "budget" in h["excerpt"]["after"]
    e = client.post(f"/api/history/{sid}/recover").json()
    assert e["finalized"] and e["total"] == 0 and "récupéré" in e["error"]
    seg = client.get("/api/session/transcript").json()["segments"]
    assert [(s["start"], s["end"], s["text"]) for s in seg] == [(1.0, 6.0, "Bonjour à tous."), (6.0, 11.0, "On commence par le budget.")]
    client.delete("/api/session")
    assert not client.get("/api/history").json()["sessions"][0]["interrupted"]


def test_lire_copie_ignore_les_lignes_vides():
    assert lire_copie("\n[00:01:00]  \nbruit\n[01:00:00] Fin", duree=3605) [0].end == 3605
    assert len(lire_copie("")) == 0
    assert BLOC  # import gardé pour les sources factices


# --- point 2 : modèle préchargé, corrections reportées, annuler, place sur le disque ---------------------------

def _faux_modele(tmp_path, monkeypatch, delai=0.3):
    modele = tmp_path / "modele"
    modele.mkdir()
    for nom in ("config.json", "model.bin", "tokenizer.json"):
        (modele / nom).write_text("{}")
    crees = []

    class Faux:
        device, compute_type = "cpu", "int8"

        def __init__(self, chemin, acceleration="auto", **_):
            time.sleep(delai)  # le chargement d'un vrai modèle prend plusieurs secondes
            crees.append((chemin, acceleration))

        def configure(self, vad_filter, glossary):
            self.glossary = glossary

        def transcribe(self, pcm, sample_rate, offset, language):
            return []
    monkeypatch.setattr("snappy.transcription.whisper.LocalWhisperProvider", Faux)
    return str(modele), crees


def test_modele_precharge_puis_reutilise(client, tmp_path, monkeypatch):
    chemin, crees = _faux_modele(tmp_path, monkeypatch)
    e = client.post("/api/model/preload", json={"model_path": chemin}).json()
    assert e["state"] == "loading"
    client.post("/api/model/preload", json={"model_path": chemin})  # rappel : pas de second chargement
    fin = time.monotonic() + 3
    while client.get("/api/model/preload").json()["state"] != "ready" and time.monotonic() < fin:
        time.sleep(0.05)
    assert client.get("/api/model/preload").json() == {"state": "ready", "message": "", "device": "CPU · int8"}
    for glossaire in ("Traceline", "Jabber"):  # deux sessions de suite : toujours le même modèle, réglages à jour
        r = client.post("/api/session/start", json={**DEMARRAGE, "engine": "local", "model_path": chemin, "glossary": glossaire})
        assert r.status_code == 200
        assert manager.current.provider.glossary == glossaire
        client.post("/api/session/stop")
        attendre(client, lambda e: e["finalized"])
        client.delete("/api/session")
    assert crees == [(chemin, "auto")]
    client.post("/api/model/preload", json={"model_path": chemin, "acceleration": "cpu"})  # autre réglage : rechargé
    manager.modele.obtenir((chemin, "cpu"))
    assert crees == [(chemin, "auto"), (chemin, "cpu")]


def test_demarrer_pendant_le_prechargement_attend_le_modele(client, tmp_path, monkeypatch):
    chemin, crees = _faux_modele(tmp_path, monkeypatch, delai=0.8)
    client.post("/api/model/preload", json={"model_path": chemin})
    assert client.post("/api/session/start", json={**DEMARRAGE, "engine": "local", "model_path": chemin}).status_code == 200
    assert len(crees) == 1
    client.post("/api/session/stop")


def test_preload_modele_absent(client, tmp_path):
    r = client.post("/api/model/preload", json={"model_path": str(tmp_path / "absent")})
    assert r.status_code == 422


def test_correction_reportee_dans_les_deux_textes_puis_annulee(client, monkeypatch):
    from snappy.models import TranscriptSegment, TranscriptWord
    session_terminee(client)
    s = manager.current
    raw = s.raw_segments
    origine = raw[0].text
    # une phrase du texte seul découpée en deux répliques, les autres en une seule
    r0 = raw[0]
    milieu = (r0.start + r0.end) / 2
    s.diarized_segments = [TranscriptSegment(r0.start, milieu, "Bonjour à tous", "SPEAKER_00", (TranscriptWord(r0.start, milieu, "x"),)),
                           TranscriptSegment(milieu, r0.end, "et bienvenue", "SPEAKER_01", ())] + \
                          [TranscriptSegment(x.start, x.end, x.text, "SPEAKER_00", ()) for x in raw[1:]]
    s.diar.status = "DONE"
    client.put("/api/session/segment", json={"variant": "diarized", "index": 1, "text": "et bienvenue à Traceline"})
    texte = lambda v: [x["text"] for x in client.get("/api/session/transcript", params={"variant": v}).json()["segments"]]  # noqa: E731
    assert texte("raw")[0] == "Bonjour à tous et bienvenue à Traceline"  # la phrase d'origine est refaite
    client.put("/api/session/segment", json={"variant": "raw", "index": 1, "text": "Deuxième phrase corrigée"})
    assert texte("diarized")[2] == "Deuxième phrase corrigée"  # une seule réplique : reportée
    client.put("/api/session/segment", json={"variant": "raw", "index": 0, "text": "Phrase coupée en deux"})
    assert texte("diarized")[:2] == ["Bonjour à tous", "et bienvenue à Traceline"]  # deux répliques : pas de report

    etat = client.get("/api/session").json()
    assert etat["can_undo"] and etat["undo_label"] == "la correction"
    assert client.post("/api/session/undo").json() == {"undone": "la correction"}
    assert texte("raw")[0] == "Bonjour à tous et bienvenue à Traceline"
    client.post("/api/session/undo")
    client.post("/api/session/undo")
    assert texte("raw")[0] == origine and texte("diarized")[1] == "et bienvenue"
    assert client.post("/api/session/undo").status_code == 409


def test_place_sur_le_disque_et_suppression_de_l_audio(client):
    fin = session_terminee(client)
    sid = fin["id"]
    client.delete("/api/session")
    h = client.get("/api/history").json()
    assert h["count"] == 1 and h["audio_size"] > 100_000 and h["size"] > h["audio_size"]
    assert h["sessions"][0]["audio"]
    assert client.post("/api/history/purge-audio", json={"days": 30}).json() == {"freed": 0, "count": 0}  # trop récente
    r = client.post("/api/history/purge-audio", json={"days": 0}).json()
    assert r["count"] == 1 and r["freed"] == h["audio_size"]
    h2 = client.get("/api/history").json()
    assert h2["audio_size"] == 0 and not h2["sessions"][0]["audio"]
    e = client.post(f"/api/history/{sid}/open").json()
    assert not e["files"]["wav"] and e["files"]["raw_txt"]  # le texte reste
    assert client.delete(f"/api/history/{sid}/audio").json() == {"freed": 0}


def test_audio_d_une_session_interrompue_protege(client):
    sid = "2026-01-02_03-04-05"
    d = sessions_dir() / sid
    d.mkdir(parents=True)
    (d / f"recording_{sid}.wav").write_bytes(b"RIFF")
    assert client.delete(f"/api/history/{sid}/audio").status_code == 409
    assert client.post("/api/history/purge-audio", json={"days": 0}).json()["count"] == 0


# --- Modèle d'identification des intervenants fourni par l'équipe (Studio Dock) --------------------------------

def _pipeline(dossier):
    for f in ("config.yaml", "embedding/pytorch_model.bin", "segmentation/pytorch_model.bin", "plda/plda.npz", "plda/xvec_transform.npz"):
        (dossier / f).parent.mkdir(parents=True, exist_ok=True)
        (dossier / f).write_text("x")
    return dossier


def test_modele_intervenants_de_l_equipe_utilise_d_office(client, tmp_path, monkeypatch):
    ia = tmp_path / "ia"
    ia.mkdir()
    pipeline = _pipeline(tmp_path / "modeles" / "intervenants" / "pyannote-community-1")
    (ia / "intervenants.json").write_text(json.dumps({"format": 1, "name": "Pyannote (équipe)", "version": "1.0.0", "path": str(pipeline)}))
    monkeypatch.setenv("STUDIODOCK_IA", str(ia))
    m = client.get("/api/model").json()
    assert m["team_diarization"] == {"name": "Pyannote (équipe)", "version": "1.0.0", "path": str(pipeline)}
    etat = client.post("/api/session/start", json={**DEMARRAGE, "diarization": True, "diarization_model_path": ""}).json()
    assert etat["diarization"]["wanted"] and not etat["diarization"]["note"]
    assert manager.current.diar_model_path == str(pipeline)
    client.post("/api/session/stop")


def test_sans_modele_intervenants_explique_quoi_faire(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIODOCK_IA", str(tmp_path / "vide"))
    assert client.get("/api/model").json()["team_diarization"] is None
    etat = client.post("/api/session/start", json={**DEMARRAGE, "diarization": True, "diarization_model_path": ""}).json()
    assert not etat["diarization"]["wanted"] and "aucun modèle d'identification" in etat["diarization"]["note"]
    client.post("/api/session/stop")


def test_resume_pour_la_barre_des_onglets(client):
    assert client.get("/api/session/brief").json() == {"active": False}
    client.post("/api/session/start", json=DEMARRAGE)
    b = client.get("/api/session/brief").json()
    assert b["active"] and b["kind"] == "live" and not b["paused"] and "segments" not in b
    client.post("/api/session/pause")
    assert client.get("/api/session/brief").json()["paused"]
    client.post("/api/session/stop")
    attendre(client, lambda e: e["finalized"])
    assert client.get("/api/session/brief").json() == {"active": False}


def test_envoyer_a_docanalyser(client, monkeypatch):
    """La transcription est déposée dans DocAnalyser (multipart, comme un import) ; l'adresse ouvre l'import."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    recu: dict = {}

    class Faux(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, data):
            corps = json.dumps(data).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps))); self.end_headers(); self.wfile.write(corps)

        def do_GET(self):
            self._json({"status": "ok", "app": "docanalyser"})

        def do_POST(self):
            recu["type"] = self.headers["Content-Type"]
            recu["corps"] = self.rfile.read(int(self.headers["Content-Length"]))
            self._json({"id": "doc-42"})

    serveur = HTTPServer(("127.0.0.1", 0), Faux)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{serveur.server_port}"
    monkeypatch.setenv("DOCANALYSER_URL", base)
    try:
        assert client.get("/api/docanalyser").json()["available"]
        client.post("/api/session/start", json=DEMARRAGE)
        assert client.post("/api/session/docanalyser").status_code == 409  # pas terminée
        client.post("/api/session/stop")
        attendre(client, lambda e: e["finalized"])
        session_terminee(client, diariser=True, monkeypatch=monkeypatch)
        client.put("/api/session/speakers", json={"names": {"SPEAKER_00": "Marie"}})
        client.put("/api/session/title", json={"title": "Atelier : parcours"})
        r = client.post("/api/session/docanalyser")
        assert r.status_code == 200, r.text
        assert r.json()["url"] == f"{base}/#/importer/doc-42?mode=transcript&from=Snappy%20Transcript"
        assert recu["type"].startswith("multipart/form-data; boundary=")
        assert b'name="file"' in recu["corps"] and b"Atelier - parcours.txt" in recu["corps"]
        assert "Atelier : parcours\nDate : ".encode() in recu["corps"] and b"[00:00:0" in recu["corps"]
        assert "Intervenants : Marie, SPEAKER_01".encode() in recu["corps"] and "Marie: ".encode() in recu["corps"]
    finally:
        serveur.shutdown()
    monkeypatch.setenv("DOCANALYSER_URL", "http://127.0.0.1:9")
    r = client.post("/api/session/docanalyser")
    assert r.status_code == 503 and "Studio Dock" in r.json()["detail"]

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

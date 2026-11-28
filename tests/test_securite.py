"""Garde-fous de l'API locale : DNS rebinding, requêtes d'un autre site (CSRF), affichage dans une page tierce."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app, base_url="http://127.0.0.1")


def test_hote_inconnu_refuse_dns_rebinding():
    assert client.get("/api/settings", headers={"host": "piege.example.com"}).status_code == 403
    assert client.get("/api/history", headers={"host": "piege.example.com:8110"}).status_code == 403
    assert client.get("/health", headers={"host": "localhost:8110"}).status_code == 200
    assert client.get("/health", headers={"host": "[::1]:8110"}).status_code == 200


def test_modification_depuis_un_autre_site_refusee():
    # un site tiers qui tente de démarrer un enregistrement, d'effacer l'audio ou de relancer une identification
    for chemin in ("/api/session/start", "/api/history/purge-audio", "/api/session/stop", "/api/model/preload"):
        r = client.post(chemin, json={}, headers={"origin": "https://piege.example.com"})
        assert r.status_code == 403, chemin
    # une autre app locale (autre port) non plus
    assert client.post("/api/session/stop", headers={"origin": "http://127.0.0.1:8020"}).status_code == 403
    # sans Origin mais marqué « autre site » par le navigateur
    assert client.post("/api/session/stop", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    # l'interface elle-même (même origine), ou un outil sans navigateur (Studio Dock, curl) : accepté
    assert client.post("/api/session/stop", headers={"origin": "http://127.0.0.1"}).status_code != 403
    assert client.post("/api/session/stop", headers={"sec-fetch-site": "same-origin"}).status_code != 403
    assert client.post("/api/session/stop").status_code != 403
    # lecture (GET) : pas concernée (le navigateur empêche un autre site de lire la réponse)
    assert client.get("/api/settings", headers={"origin": "https://piege.example.com"}).status_code == 200


def test_entetes_de_protection():
    r = client.get("/health")
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cross-origin-resource-policy"] == "same-origin" and r.headers["x-content-type-options"] == "nosniff"

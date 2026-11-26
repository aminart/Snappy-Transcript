"""Envoi d'une transcription à DocAnalyser (suite Studio Dock), pour en faire une synthèse.

Snappy dépose le texte dans DocAnalyser (POST /api/v2/documents, comme un import), puis l'interface ouvre
DocAnalyser sur #/importer/<id>?mode=transcript : le document est dans la liste, « Synthèse de transcription »
est choisie, il ne reste qu'à lancer. Tout reste sur ce poste (127.0.0.1).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from urllib import error, request
from urllib.parse import quote

ADRESSE = "http://127.0.0.1:8020"  # port de DocAnalyser dans le catalogue Studio Dock


class Injoignable(Exception):
    pass


def adresse() -> str:
    return (os.environ.get("DOCANALYSER_URL") or ADRESSE).rstrip("/")


def _lire(req: request.Request, delai: float) -> dict:
    with request.urlopen(req, timeout=delai) as r:  # noqa: S310 — adresse locale
        return json.loads(r.read().decode("utf-8"))


def disponible(base: str | None = None) -> bool:
    try:
        return _lire(request.Request(f"{base or adresse()}/health"), 1.5).get("app") == "docanalyser"
    except (OSError, ValueError):
        return False


def envoyer(contenu: bytes, titre: str, base: str | None = None) -> str:
    """Dépose le fichier et renvoie l'adresse à ouvrir dans le navigateur."""
    base = base or adresse()
    if not disponible(base):
        raise Injoignable("DocAnalyser n'est pas lancé. Ouvrez-le depuis Studio Dock, puis réessayez.")
    nom = (re.sub(r'[\\/:*?"<>|\n\r]+', "-", titre).strip() or "Transcription")[:120] + ".txt"
    borne = uuid.uuid4().hex
    corps = (f'--{borne}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="{nom.replace(chr(34), "")}"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n').encode() + contenu + f"\r\n--{borne}--\r\n".encode()
    req = request.Request(f"{base}/api/v2/documents", data=corps, method="POST",
                          headers={"Content-Type": f"multipart/form-data; boundary={borne}"})
    try:
        doc = _lire(req, 30)
    except error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
        except ValueError:
            detail = None
        raise Injoignable(f"DocAnalyser a refusé le fichier : {detail or e.reason}") from e
    except (OSError, ValueError) as e:
        raise Injoignable("DocAnalyser ne répond pas. Vérifiez qu'il est lancé, puis réessayez.") from e
    return f"{base}/#/importer/{doc['id']}?mode=transcript&from={quote('Snappy Transcript')}"

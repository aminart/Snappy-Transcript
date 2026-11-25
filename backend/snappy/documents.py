"""Outils autour du texte d'une session : export Word, rechercher / remplacer, extraits pour « Mes transcriptions »,
forme d'onde du lecteur et relecture de la copie de récupération."""
from __future__ import annotations

import re
import unicodedata
import wave
import zipfile
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from .export import timestamp
from .models import TranscriptSegment

# --- Rechercher / remplacer ----------------------------------------------------------------------------------


def motif(cherche: str, casse: bool = False, mot_entier: bool = False) -> re.Pattern[str]:
    """Expression régulière d'une recherche littérale (les caractères spéciaux sont échappés)."""
    corps = re.escape(cherche)
    if mot_entier:
        corps = rf"(?<!\w){corps}(?!\w)"
    return re.compile(corps, 0 if casse else re.IGNORECASE)


def remplacer(texte: str, m: re.Pattern[str], par: str) -> tuple[str, int]:
    return m.subn(lambda _: par, texte)


# --- Recherche dans « Mes transcriptions » -------------------------------------------------------------------

def sans_accents(texte: str) -> str:
    """Minuscules sans accents, même longueur que le texte d'origine (les positions restent valables)."""
    return "".join((unicodedata.normalize("NFD", c)[0] if c.strip() else c) for c in texte).lower()


def extrait(texte: str, q: str = "", largeur: int = 70) -> dict | None:
    """Extrait autour de la première occurrence de q (accents et majuscules ignorés) ; sans q, le début du texte.
    Renvoie {"before", "match", "after"} pour que l'interface surligne le mot trouvé, ou None si q est absent."""
    texte = " ".join(texte.split())
    if not q.strip():
        coupe = texte[: largeur * 2]
        return {"before": "", "match": "", "after": coupe + ("…" if len(texte) > len(coupe) else "")}
    i = sans_accents(texte).find(sans_accents(q.strip()))
    if i < 0:
        return None
    j = i + len(q.strip())
    debut = max(0, texte.rfind(" ", 0, max(0, i - largeur)) + 1) if i > largeur else 0
    fin = texte.find(" ", min(len(texte), j + largeur))
    fin = len(texte) if fin < 0 else fin
    return {"before": ("… " if debut else "") + texte[debut:i], "match": texte[i:j],
            "after": texte[j:fin] + (" …" if fin < len(texte) else "")}


def compter(texte: str, q: str) -> int:
    return sans_accents(texte).count(sans_accents(q.strip())) if q.strip() else 0


# --- Export Word (.docx), sans dépendance : un document WordprocessingML minimal ----------------------------

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:lang w:val="fr-FR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="80"/></w:pPr><w:rPr><w:b/><w:sz w:val="40"/><w:color w:val="1B1D2A"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="360"/></w:pPr><w:rPr><w:color w:val="4A4E61"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="0F1D96"/></w:rPr></w:style>
</w:styles>"""


def _run(texte: str, gras: bool = False, gris: bool = False) -> str:
    props = ("<w:b/>" if gras else "") + ('<w:color w:val="5A5F73"/><w:sz w:val="18"/>' if gris else "")
    return f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}<w:t xml:space="preserve">{escape(texte)}</w:t></w:r>'


def _para(contenu: str, style: str = "", fond: str = "") -> str:
    ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fond}"/>' if fond else "")
    return f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{contenu}</w:p>"


def segments_to_docx(segments: list[TranscriptSegment], titre: str, sous_titre: str = "",
                     marques: list[dict] | None = None) -> bytes:
    """Document Word : titre, informations, moments marqués, puis une réplique par paragraphe (heure, intervenant)."""
    corps = [_para(_run(titre), "Title")]
    if sous_titre:
        corps.append(_para(_run(sous_titre), "Subtitle"))
    marques = marques or []
    if marques:
        corps.append(_para(_run("Moments marqués"), "Heading2"))
        for m in marques:
            corps.append(_para(_run(f"{timestamp(m['t'])}  ", gris=True) + _run(m.get("label") or "")))
        corps.append(_para(_run("Transcription"), "Heading2"))
    temps_marques = sorted(m["t"] for m in marques)
    for i, s in enumerate(segments):
        fin = segments[i + 1].start if i + 1 < len(segments) else float("inf")
        marque = any(s.start <= t < fin for t in temps_marques)
        contenu = _run(f"{timestamp(s.start)}  ", gris=True) + (_run(f"{s.speaker} : ", gras=True) if s.speaker else "") + _run(s.text)
        corps.append(_para(contenu, fond="EEF0FB" if marque else ""))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                + "".join(corps) +
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" '
                'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + escape(titre) + '</dc:title>'
            '<dc:creator>Snappy Transcript</dc:creator></cp:coreProperties>')
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("docProps/core.xml", core)
    return out.getvalue()


# --- Forme d'onde --------------------------------------------------------------------------------------------

def forme_onde(wav: Path, n: int = 240) -> tuple[list[float], float]:
    """n crêtes (0..1) réparties sur l'enregistrement, et sa durée en secondes. Lecture par blocs : pas de pic mémoire."""
    with wave.open(str(wav), "rb") as w:
        trames, taux, canaux = w.getnframes(), w.getframerate(), w.getnchannels()
        if not trames:
            return [0.0] * n, 0.0
        par_case = max(1, trames // n)
        cretes = []
        for _ in range(n):
            brut = w.readframes(par_case)
            if not brut:
                cretes.append(0.0)
                continue
            x = np.frombuffer(brut, dtype=np.int16)
            cretes.append(float(np.abs(x.astype(np.int32)).max()) / 32768.0 if x.size else 0.0)
        haut = max(cretes) or 1.0
        return [round(min(1.0, c / haut), 3) for c in cretes], trames / taux


# --- Copie de récupération -----------------------------------------------------------------------------------

_LIGNE = re.compile(r"^\[(\d+):(\d\d):(\d\d)\]\s?(.*)$")


def lire_copie(texte: str, duree: float | None = None) -> list[TranscriptSegment]:
    """Relit la copie de récupération (« [00:01:02] texte ») ; chaque phrase finit où commence la suivante."""
    debuts: list[tuple[float, str]] = []
    for ligne in texte.splitlines():
        m = _LIGNE.match(ligne.strip())
        if m and m.group(4).strip():
            debuts.append((int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)), m.group(4).strip()))
    out = []
    for i, (debut, txt) in enumerate(debuts):
        fin = debuts[i + 1][0] if i + 1 < len(debuts) else (duree if duree and duree > debut else debut + 5)
        out.append(TranscriptSegment(float(debut), float(max(fin, debut + 0.5)), txt, None, ()))
    return out


def duree_wav(wav: Path) -> float | None:
    try:
        with wave.open(str(wav), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (OSError, wave.Error, EOFError):
        return None

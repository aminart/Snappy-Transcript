"""Test de la source avant de démarrer : on ouvre le micro (et / ou l'application) sans rien enregistrer, pour
afficher « On vous entend » / « Teams est bien capté ». L'aperçu s'arrête seul si l'interface ne le consulte plus."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

SEUIL_SON = 0.25       # niveau (0..1, échelle -60..0 dBFS) au-dessus duquel « on entend » quelque chose
SANS_NOUVELLES = 6.0   # s sans consultation : l'aperçu se ferme (page quittée, onglet fermé)


def niveau(block: bytes) -> float:
    """Même échelle que le vu-mètre de la session : efficace en dBFS ramené de [-60 ; 0] à [0 ; 1]."""
    x = np.frombuffer(block, dtype=np.int16)
    if not x.size:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(x.astype(np.float32))))) / 32768.0
    db = 20 * np.log10(max(rms, 1e-6))
    return float(min(1.0, max(0.0, (db + 60) / 60)))


class _Mesure:
    def __init__(self, nom: str, source: Any):
        self.nom, self.source = nom, source
        self.level, self.entendu, self.erreur = 0.0, False, ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def demarrer(self) -> None:
        self.source.start()

        def boucle():
            try:
                while not self._stop.is_set():
                    b = self.source.read_chunk(0.2)
                    if b:
                        self.level = niveau(b)
                        self.entendu = self.entendu or self.level >= SEUIL_SON
            except Exception as exc:  # micro débranché, application fermée…
                self.erreur = str(exc)
                log.warning("Aperçu %s : %s", self.nom, exc)

        self._thread = threading.Thread(target=boucle, name=f"apercu-{self.nom}", daemon=True)
        self._thread.start()

    def arreter(self) -> None:
        self._stop.set()
        try:
            self.source.stop()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=1)

    def etat(self) -> dict[str, Any]:
        return {"level": round(self.level, 3), "heard": self.entendu, "error": self.erreur}


class Apercu:
    """Une seule vérification à la fois ; `fabriquer` reçoit les réglages et renvoie {"voix": source, "autre": source}."""

    def __init__(self) -> None:
        self._mesures: dict[str, _Mesure] = {}
        self._cle: Any = None
        self._derniere = 0.0
        self._lock = threading.RLock()
        self._garde: threading.Thread | None = None

    @property
    def actif(self) -> bool:
        return bool(self._mesures)

    def demarrer(self, cle: Any, fabriquer: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            self._derniere = time.monotonic()
            if self._mesures and cle == self._cle:
                return self.etat()
            self.arreter()
            mesures = {}
            try:
                for nom, source in fabriquer().items():
                    m = _Mesure(nom, source)
                    m.demarrer()
                    mesures[nom] = m
            except BaseException:
                for m in mesures.values():
                    m.arreter()
                raise
            self._mesures, self._cle = mesures, cle
            if not self._garde or not self._garde.is_alive():
                self._garde = threading.Thread(target=self._surveiller, name="apercu-garde", daemon=True)
                self._garde.start()
            return self.etat()

    def _surveiller(self) -> None:
        while True:
            time.sleep(1)
            with self._lock:
                if not self._mesures:
                    return
                if time.monotonic() - self._derniere > SANS_NOUVELLES:
                    self.arreter()
                    return

    def etat(self) -> dict[str, Any]:
        with self._lock:
            self._derniere = time.monotonic()
            return {"active": bool(self._mesures), **{nom: m.etat() for nom, m in self._mesures.items()}}

    def arreter(self) -> None:
        with self._lock:
            for m in self._mesures.values():
                m.arreter()
            self._mesures, self._cle = {}, None

"""Son d'une seule application (Teams, Zoom, Chrome…) sous Windows.

Deux briques :
- `list_audio_apps()` liste les applications qui ont ouvert une session audio (sur toutes les sorties), regroupées
  par application racine (Teams joue son son dans un sous-processus msedgewebview2, Chrome dans un processus
  « utility » : on remonte au programme que l'utilisateur reconnaît), avec leur niveau sonore du moment ;
- `ProcessLoopbackSource` capte le son de cette application et de ses sous-processus, sans le reste (notifications,
  musique…), grâce à la capture « process loopback » de WASAPI (Windows 10 version 2004 et suivantes).

Rien ici n'est importé hors de Windows : le regroupement est une fonction pure, testée sur toutes les plateformes.
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

import numpy as np

from .base import AudioSource

log = logging.getLogger(__name__)

BUILD_MINIMUM = 19041  # Windows 10 version 2004

# Parents qui ne sont pas « l'application » : on s'arrête avant eux en remontant l'arbre des processus.
HOTES = {"explorer.exe", "svchost.exe", "services.exe", "wininit.exe", "winlogon.exe", "sihost.exe",
         "runtimebroker.exe", "userinit.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe",
         "windowsterminal.exe", "openconsole.exe", "applicationframehost.exe", "smss.exe", "csrss.exe", "system"}

# Applications de réunion : « Ma voix + une application » est recommandé quand l'une d'elles fait du son.
VISIO = {"ms-teams.exe", "teams.exe", "zoom.exe", "webex.exe", "ciscocollabhost.exe", "atmgr.exe", "ciscojabber.exe",
         "slack.exe", "skype.exe", "lync.exe", "discord.exe", "gotomeeting.exe", "g2mcomm.exe", "webexmta.exe"}

NOMS_CONNUS = {"ms-teams.exe": "Microsoft Teams", "teams.exe": "Microsoft Teams", "zoom.exe": "Zoom",
               "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge", "firefox.exe": "Firefox",
               "ciscojabber.exe": "Cisco Jabber", "ciscocollabhost.exe": "Webex", "webex.exe": "Webex",
               "slack.exe": "Slack", "spotify.exe": "Spotify", "vlc.exe": "VLC", "outlook.exe": "Outlook",
               "olk.exe": "Outlook", "discord.exe": "Discord"}

SEUIL_SON = 0.003  # crête au-delà de laquelle l'application « fait du son »


@dataclass
class AppAudio:
    exe: str          # nom du programme en minuscules (« ms-teams.exe ») : c'est lui qui est mémorisé
    name: str         # nom lisible (« Microsoft Teams »)
    pid: int          # processus racine : la capture inclut ses sous-processus
    active: bool      # une de ses sessions joue en ce moment
    level: float      # crête 0..1
    visio: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["level"] = round(self.level, 3)
        return d


def windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def app_capture_status() -> tuple[bool, str]:
    """(possible sur ce poste, raison sinon) — affichée telle quelle par l'interface."""
    if sys.platform != "win32":
        return False, "Le son d'une application ne peut être capté que sous Windows."
    if windows_build() < BUILD_MINIMUM:
        return False, ("Cet ordinateur ne sait pas isoler le son d'une application (il faut Windows 10 version 2004 ou "
                       "plus récent, ou Windows 11). Choisissez « Tout le son de l'ordinateur ».")
    import importlib.util
    if importlib.util.find_spec("comtypes") is None or importlib.util.find_spec("psutil") is None:
        return False, "Le son d'une application n'est pas disponible dans cette installation (comtypes ou psutil manquant)."
    return True, ""


def nom_lisible(exe: str, description: str = "") -> str:
    if exe in NOMS_CONNUS:
        return NOMS_CONNUS[exe]
    if description.strip():
        return description.strip()
    stem = exe[:-4] if exe.endswith(".exe") else exe
    return stem.replace("-", " ").replace("_", " ").strip().title() or exe


def regrouper(sessions: Iterable[tuple[int, bool, float]], parent: Callable[[int], int | None],
              exe_de: Callable[[int], str | None], description_de: Callable[[int], str] = lambda pid: "",
              exclus: set[int] = frozenset()) -> list[AppAudio]:
    """Regroupe des sessions audio (pid, active, crête) par application racine.

    `parent(pid)` renvoie le pid parent (None s'il n'existe plus), `exe_de(pid)` le nom du programme (None si le
    processus a disparu). On remonte tant que le parent existe et n'est pas un hôte du système (explorateur,
    svchost…). Les processus de `exclus` (Snappy lui-même) et leurs descendants sont ignorés.
    """
    def racine(pid: int) -> int | None:
        courant, vus = pid, set()
        for _ in range(32):
            if courant in exclus:
                return None
            vus.add(courant)
            p = parent(courant)
            if p is None or p in (0, 4) or p in vus:
                return courant
            if p in exclus:
                return None
            exe_parent = (exe_de(p) or "").lower()
            if not exe_parent or exe_parent in HOTES:
                return courant
            courant = p
        return courant

    apps: dict[int, AppAudio] = {}
    for pid, active, crete in sessions:
        if pid in (0, 4):  # « Sons système » de Windows
            continue
        r = racine(pid)
        if r is None:
            continue
        exe = (exe_de(r) or "").lower()
        if not exe:
            continue
        a = apps.get(r)
        if a is None:
            apps[r] = a = AppAudio(exe, nom_lisible(exe, description_de(r)), r, False, 0.0, exe in VISIO)
        a.level = max(a.level, float(crete))
        a.active = a.active or (active and crete >= SEUIL_SON)
    return sorted(apps.values(), key=lambda a: (not a.active, -a.level, a.name.lower()))


def choisir(apps: list[AppAudio], exe: str) -> AppAudio | None:
    """L'application mémorisée (par son programme) parmi celles ouvertes ; la plus sonore s'il y en a plusieurs."""
    exe = exe.lower().strip()
    return next((a for a in apps if a.exe == exe), None)


def recommandee(apps: list[AppAudio]) -> AppAudio | None:
    """Une application de réunion qui fait du son, sinon la première de réunion ouverte."""
    return next((a for a in apps if a.visio and a.active), None) or next((a for a in apps if a.visio), None)


def vers_mono(pcm: np.ndarray, canaux: int, taux: int, cible: int = 16000) -> np.ndarray:
    """PCM16 entrelacé → mono à `cible` Hz (moyenne des canaux, rééchantillonnage linéaire)."""
    if canaux > 1:
        n = len(pcm) // canaux
        x = pcm[: n * canaux].reshape(n, canaux).astype(np.float32).mean(axis=1)
    else:
        x = pcm.astype(np.float32)
    if taux != cible and len(x):
        if taux % cible == 0:  # 48 kHz → 16 kHz : moyenne par paquets (filtre passe-bas simple)
            k = taux // cible
            m = len(x) // k
            x = x[: m * k].reshape(m, k).mean(axis=1)
        else:
            m = int(round(len(x) * cible / taux))
            x = np.interp(np.linspace(0, len(x) - 1, m), np.arange(len(x)), x) if m else x[:0]
    return np.clip(x, -32768, 32767).astype(np.int16)


# --- Windows ------------------------------------------------------------------------------------------------

def _description(chemin: str) -> str:
    """« FileDescription » des propriétés du programme (« Microsoft Teams »), vide si absente."""
    try:
        version = ctypes.windll.version
        taille = version.GetFileVersionInfoSizeW(chemin, None)
        if not taille:
            return ""
        tampon = ctypes.create_string_buffer(taille)
        if not version.GetFileVersionInfoW(chemin, 0, taille, tampon):
            return ""
        ptr, n = ctypes.c_void_p(), ctypes.c_uint()
        if not version.VerQueryValueW(tampon, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) or n.value < 4:
            return ""
        lang, page = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
        cle = f"\\StringFileInfo\\{lang:04x}{page:04x}\\FileDescription"
        if not version.VerQueryValueW(tampon, cle, ctypes.byref(ptr), ctypes.byref(n)) or not n.value:
            return ""
        return ctypes.wstring_at(ptr, n.value).rstrip("\x00")
    except Exception:
        return ""


def _sessions_windows() -> list[tuple[int, bool, float]]:
    from . import _wasapi as w
    out: list[tuple[int, bool, float]] = []
    for pid, active, crete in w.sessions_audio():
        out.append((pid, active, crete))
    return out


def list_audio_apps() -> list[AppAudio]:
    """Applications ouvertes qui utilisent le son ; [] hors de Windows ou en cas d'échec (jamais d'exception)."""
    ok, _ = app_capture_status()
    if not ok:
        return []
    try:
        import psutil
        from .system_audio import _com_initialized

        with _com_initialized():
            sessions = _sessions_windows()

        cache: dict[int, Any] = {}

        def proc(pid: int):
            if pid not in cache:
                try:
                    cache[pid] = psutil.Process(pid)
                except (psutil.Error, ValueError):
                    cache[pid] = None
            return cache[pid]

        def parent(pid: int) -> int | None:
            p = proc(pid)
            try:
                return p.ppid() if p else None
            except psutil.Error:
                return None

        def exe_de(pid: int) -> str | None:
            p = proc(pid)
            try:
                return p.name() if p else None
            except psutil.Error:
                return None

        def description_de(pid: int) -> str:
            p = proc(pid)
            try:
                return _description(p.exe()) if p else ""
            except psutil.Error:
                return ""

        return regrouper(sessions, parent, exe_de, description_de, exclus={os.getpid()})
    except Exception as exc:
        log.warning("Liste des applications audio indisponible : %s: %s", type(exc).__name__, exc)
        return []


class ProcessLoopbackSource(AudioSource):
    """Son d'une application et de ses sous-processus, en PCM16 mono à `sample_rate` Hz."""

    def __init__(self, pid: int, name: str = "", sample_rate: int = 16000, block_ms: int = 100):
        self.pid, self.name = int(pid), name or f"processus {pid}"
        self.sample_rate, self.blocksize = sample_rate, int(sample_rate * block_ms / 1000)
        self._q: queue.Queue = queue.Queue(maxsize=200)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _put(self, x) -> None:
        try:
            self._q.put_nowait(x)
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.put_nowait(x)
            except queue.Empty:
                pass

    def start(self) -> None:
        """Ouvre la capture ; lève OSError avec un message clair si Windows la refuse (ex. système trop ancien)."""
        self._stop.clear()
        pret: dict[str, Any] = {}
        evenement = threading.Event()

        def run():
            from . import _wasapi as w
            try:
                with w.com_mta():
                    capture = w.CaptureProcessus(self.pid)
                    pret["ok"] = True
                    evenement.set()
                    reste = np.zeros(0, dtype=np.int16)
                    with capture:
                        while not self._stop.is_set():
                            for brut in capture.lire(200):
                                mono = vers_mono(np.frombuffer(brut, dtype=np.int16), capture.canaux, capture.taux, self.sample_rate)
                                reste = np.concatenate([reste, mono])
                            while len(reste) >= self.blocksize:
                                self._put(reste[: self.blocksize].tobytes())
                                reste = reste[self.blocksize:]
            except Exception as exc:
                log.exception("Capture du son de l'application impossible")
                if not evenement.is_set():
                    pret["erreur"] = exc
                    evenement.set()
                else:
                    self._put(RuntimeError(f"Capture du son de {self.name} interrompue : {exc}"))

        self._thread = threading.Thread(target=run, name="app-loopback", daemon=True)
        self._thread.start()
        if not evenement.wait(8):
            self._stop.set()
            raise OSError(f"Windows ne répond pas pour capter le son de {self.name}.")
        if "erreur" in pret:
            self._thread = None
            raise OSError(f"Windows refuse de capter le son de {self.name} ({pret['erreur']}). "
                          "Choisissez « Tout le son de l'ordinateur ».")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def read_chunk(self, timeout: float = 0.2) -> bytes | None:
        try:
            x = self._q.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(x, Exception):
            raise x
        return x

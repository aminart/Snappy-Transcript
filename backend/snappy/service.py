"""Orchestration d'une session : démarrage, exports bruts, diarisation en arrière-plan, reprise après coup.

Contrairement à l'ancienne interface Streamlit, rien ici ne dépend d'un navigateur ouvert : un thread de
finalisation écrit les exports dès que la transcription est terminée, et la diarisation tourne ensuite seule.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .audio.microphone import MicrophoneSource
from .audio.system_audio import MixedAudioSource, SystemAudioSource
from .config import CONFIG
from .export import segments_to_srt, segments_to_txt, timestamp
from .apercu import Apercu
from .file_session import FileTranscription
from .models import TranscriptSegment
from .paths import app_data_dir
from .session import LiveSession
from .transcription.mock import MockProvider

log = logging.getLogger(__name__)

# pyannote est lourd (mémoire, CPU) : une seule diarisation à la fois, les autres attendent leur tour.
_DIARIZATION_LOCK = threading.Lock()


class ServiceError(Exception):
    """Erreur destinée à l'utilisateur, avec le code HTTP à renvoyer."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class StartParams:
    source: str = "microphone"           # microphone | system | mixed
    engine: str = "local"                # local | mock
    input_device: int | None = None
    output_device: str = ""
    app: str = ""                        # programme dont on capte le son (« ms-teams.exe ») ; vide : tout le son
    model_path: str = ""
    acceleration: str = "auto"
    language: str = "fr"
    glossary: str = ""
    chunk_seconds: int = 5
    overlap_seconds: float = 0.75
    vad_filter: bool = True
    save_audio: bool = True
    diarization: bool = True
    diarization_model_path: str = ""
    speaker_hint: int = 0


def segment_from_dict(d: dict[str, Any]) -> TranscriptSegment:
    from .models import TranscriptWord
    return TranscriptSegment(float(d["start"]), float(d["end"]), str(d["text"]), d.get("speaker"),
                             tuple(TranscriptWord(float(a), float(b), str(t)) for a, b, t in d.get("words") or []))


def segment_to_dict(seg: TranscriptSegment, words: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text, "speaker": seg.speaker}
    if words:
        out["words"] = [[round(w.start, 3), round(w.end, 3), w.text] for w in seg.words]
    return out


# --- Diarisation --------------------------------------------------------------------------------------------

class DiarizationJob:
    """Suivi d'une diarisation (de la session courante ou d'une reprise après coup)."""

    def __init__(self) -> None:
        self.status = "IDLE"          # IDLE | RUNNING | DONE | ERROR
        self.phase = ""
        self.fraction: float | None = None
        self.elapsed = 0.0
        self.eta: float | None = None
        self.error = ""
        self.note = ""
        self.thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.status == "RUNNING"

    def progress(self, phase: str, fraction: float | None, elapsed: float, eta: float | None) -> None:
        self.phase, self.fraction, self.elapsed, self.eta = phase, fraction, elapsed, eta

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "phase": self.phase, "fraction": self.fraction, "elapsed": round(self.elapsed, 1),
                "eta": None if self.eta is None else round(self.eta, 1), "error": self.error, "note": self.note}


def _diarize(wav: Path, segments: list[TranscriptSegment], model_path: str, speakers: int, job: DiarizationJob) -> list[TranscriptSegment]:
    from .diarization import diarize_wav_file

    kwargs = {"min_speakers": speakers, "max_speakers": speakers} if speakers else {}
    job.progress("en attente d'une autre diarisation", None, 0.0, None)
    with _DIARIZATION_LOCK:
        return diarize_wav_file(wav, segments, model_path, progress_callback=job.progress, **kwargs)


def _validate_pipeline(path: str) -> str:
    from .diarization import validate_diarization_model

    ok, detail = validate_diarization_model(path)
    if not ok:
        raise ServiceError(detail, 422)
    return detail


# --- Session active -----------------------------------------------------------------------------------------

class ActiveSession:
    def __init__(self, live: LiveSession, stamp: str, params: StartParams, provider: Any, diarization_note: str = ""):
        self.live, self.stamp, self.params, self.provider = live, stamp, params, provider
        self.diar = DiarizationJob()
        self.diar.note = diarization_note
        self.diar_wanted = False                      # diarisation automatique à lancer après la transcription
        self.diar_model_path = ""
        self.raw_segments: list[TranscriptSegment] | None = None
        self.diarized_segments: list[TranscriptSegment] | None = None
        self.raw_txt = self.raw_srt = self.diar_txt = self.diar_srt = None
        self.speaker_names: dict[str, str] = {}       # « SPEAKER_00 » → « Marie », repris dans les exports
        self.title = ""                               # titre donné par la personne (« Comité projet – budget »)
        self.marks: list[dict[str, Any]] = []         # moments marqués : {"t": secondes, "label": texte choisi ou ""}
        self._annulables: list[tuple[str, list, list | None]] = []  # (quoi, texte seul, avec intervenants) avant chaque modification
        self._onde: tuple[float, list[float], float] | None = None
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._exports_done = threading.Event()
        self._lock = threading.RLock()

    @property
    def finished(self) -> bool:
        """Capture et transcription terminées ET exports écrits : c'est à partir de là que tout est téléchargeable."""
        return self.live.is_finalized and self._exports_done.is_set()

    # -- finalisation : indépendante de l'interface ------------------------------------------------------------

    def watch(self) -> None:
        threading.Thread(target=self._finalize_when_done, name="finalizer", daemon=True).start()

    def _finalize_when_done(self) -> None:
        while not self.live.is_finalized:
            time.sleep(0.2)
        try:
            self._write_raw_exports()
            if self.diar_wanted and self.live.wav_path.is_file() and self.raw_segments:
                self.start_diarization(self.diar_model_path, self.params.speaker_hint)
            else:
                self._discard_wav_if_unwanted()
        except Exception as exc:  # ne jamais perdre silencieusement la fin de session
            log.exception("Finalisation de session")
            self.live.stats.last_error = f"Finalisation : {type(exc).__name__}: {exc}"
        finally:
            self._exports_done.set()

    def _write_raw_exports(self) -> None:
        with self._lock:
            if self.raw_segments is not None:
                return
            self.raw_segments = self.live.segments()
            self.save()

    # -- sauvegarde : exports, texte (pour rouvrir la session) et fiche de l'historique ------------------------

    def named(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        from dataclasses import replace
        return [replace(s, speaker=self.speaker_names.get(s.speaker, s.speaker)) if s.speaker else s for s in segments]

    def save(self) -> None:
        """Réécrit les exports et la fiche de la session (après la transcription, la diarisation, chaque correction)."""
        with self._lock:
            d = self.live.session_dir
            if self.raw_segments is not None:
                self.raw_txt, self.raw_srt = d / f"transcript_{self.stamp}_raw.txt", d / f"transcript_{self.stamp}_raw.srt"
                _write(self.raw_txt, segments_to_txt(self.raw_segments))
                _write(self.raw_srt, segments_to_srt(self.raw_segments))
                _write(d / "transcript_raw.json", json.dumps([segment_to_dict(s, True) for s in self.raw_segments], ensure_ascii=False))
            if self.diarized_segments is not None:
                nommes = self.named(self.diarized_segments)
                self.diar_txt, self.diar_srt = d / f"transcript_{self.stamp}_diarized.txt", d / f"transcript_{self.stamp}_diarized.srt"
                _write(self.diar_txt, segments_to_txt(nommes))
                _write(self.diar_srt, segments_to_srt(nommes))
                _write(d / "transcript_diarized.json",
                       json.dumps([segment_to_dict(s, True) for s in self.diarized_segments], ensure_ascii=False))
            fiche = {"format": 1, "id": self.stamp, "kind": getattr(self.live, "kind", "live"),
                     "title": self.title, "marks": self.marks_view(),
                     "name": getattr(self.live, "display_name", None), "started": self.started,
                     "duration": round(self.live.duration, 1), "language": self.params.language,
                     "segments": len(self.raw_segments or []), "diarized": self.diarized_segments is not None,
                     "speaker_names": self.speaker_names, "error": self.live.stats.last_error or ""}
            _write(d / SESSION_FILE, json.dumps(fiche, ensure_ascii=False, indent=2))

    # -- corrections -----------------------------------------------------------------------------------------

    def _editable(self, variant: str) -> list[TranscriptSegment]:
        if not self.finished:
            raise ServiceError("La session n'est pas terminée.", 409)
        if variant == "diarized":
            if self.diar.running:
                raise ServiceError("Attendez la fin de l'identification des intervenants.", 409)
            if self.diarized_segments is None:
                raise ServiceError("Les intervenants n'ont pas été identifiés pour cette session.", 404)
            return self.diarized_segments
        return self.raw_segments or []

    def _memoriser(self, quoi: str) -> None:
        """Garde l'état du texte avant une modification, pour Ctrl+Z (20 étapes)."""
        self._annulables.append((quoi, list(self.raw_segments or []),
                                 list(self.diarized_segments) if self.diarized_segments is not None else None))
        del self._annulables[:-20]

    def undo(self) -> str:
        """Annule la dernière correction ou le dernier « Tout remplacer » ; renvoie ce qui a été annulé."""
        with self._lock:
            if not self._annulables:
                raise ServiceError("Rien à annuler.", 409)
            if self.diar.running:
                raise ServiceError("Attendez la fin de l'identification des intervenants.", 409)
            quoi, self.raw_segments, self.diarized_segments = self._annulables.pop()
            self.save()
            return quoi

    @staticmethod
    def _phrase_d_origine(raw: list[TranscriptSegment], d: TranscriptSegment) -> int:
        """Index de la phrase du texte seul dont vient une réplique (le plus grand recouvrement dans le temps)."""
        meilleur, recouvrement = -1, -1.0
        for i, r in enumerate(raw):
            if r.start > d.end + 0.01:
                break
            ov = min(r.end, d.end) - max(r.start, d.start)
            if ov > recouvrement:
                meilleur, recouvrement = i, ov
        return meilleur

    def edit_segment(self, variant: str, index: int, text: str) -> dict[str, Any]:
        """Corrige le texte d'une phrase ; l'horodatage mot à mot de cette phrase est abandonné.
        La correction est reportée dans l'autre version du texte : une réplique corrigée refait la phrase du texte
        seul dont elle vient ; une phrase du texte seul n'est reportée que si elle n'a donné qu'une réplique."""
        from dataclasses import replace
        text = " ".join((text or "").split())
        if not text:
            raise ServiceError("Une phrase ne peut pas être vide.", 422)
        with self._lock:
            segments = self._editable(variant)
            if not 0 <= index < len(segments):
                raise ServiceError("Cette phrase n'existe plus : rechargez la page.", 404)
            if segments[index].text != text:
                self._memoriser("la correction")
                segments[index] = replace(segments[index], text=text, words=())
                raw, diar = self.raw_segments or [], self.diarized_segments
                if variant == "diarized" and raw:
                    i = self._phrase_d_origine(raw, segments[index])
                    if i >= 0:
                        morceaux = [d.text for d in diar if self._phrase_d_origine(raw, d) == i]
                        raw[i] = replace(raw[i], text=" ".join(morceaux), words=())
                elif variant == "raw" and diar:
                    issues = [k for k, d in enumerate(diar) if self._phrase_d_origine(raw, d) == index]
                    if len(issues) == 1:
                        diar[issues[0]] = replace(diar[issues[0]], text=text, words=())
                self.save()
            return segment_to_dict(self.named([segments[index]])[0], words=True)

    def rename_speakers(self, names: dict[str, str]) -> dict[str, str]:
        with self._lock:
            labels = {s.speaker for s in self._editable("diarized") if s.speaker}
            nouveaux = {}
            for label, nom in names.items():
                nom = " ".join(str(nom or "").split())[:40]
                if label in labels and nom and nom != label:
                    nouveaux[label] = nom
            self.speaker_names = nouveaux
            self.save()
            return self.speaker_names

    # -- titre, moments marqués, rechercher / remplacer -------------------------------------------------------

    def set_title(self, title: str) -> str:
        with self._lock:
            self.title = " ".join((title or "").split())[:120]
            if self.raw_segments is not None:
                self.save()
            return self.title

    def _texte_au_moment(self, t: float) -> str:
        """La phrase prononcée au moment marqué (la dernière commencée avant), pour nommer le moment."""
        segs = self.raw_segments if self.raw_segments is not None else self.live.segments()
        avant = [x for x in segs if x.start <= t + 0.5]
        if not avant:
            return ""
        texte = avant[-1].text
        return texte if len(texte) <= 90 else texte[:90].rsplit(" ", 1)[0] + "…"

    def marks_view(self) -> list[dict[str, Any]]:
        return [{"t": m["t"], "label": m["label"] or self._texte_au_moment(m["t"]), "named": bool(m["label"])} for m in self.marks]

    def add_mark(self, label: str = "") -> list[dict[str, Any]]:
        with self._lock:
            if self.finished or self.live.stop_requested or getattr(self.live, "kind", "live") != "live":
                raise ServiceError("On ne marque un moment que pendant un enregistrement en direct.", 409)
            t = round(self.live.duration, 1)
            if self.marks and t - self.marks[-1]["t"] < 2:  # double appui sur M
                return self.marks_view()
            self.marks.append({"t": t, "label": " ".join((label or "").split())[:120]})
            return self.marks_view()

    def edit_mark(self, index: int, label: str | None) -> list[dict[str, Any]]:
        """label None : supprime le moment ; "" : revient au nom automatique."""
        with self._lock:
            if not 0 <= index < len(self.marks):
                raise ServiceError("Ce moment n'existe plus.", 404)
            if label is None:
                self.marks.pop(index)
            else:
                self.marks[index]["label"] = " ".join(label.split())[:120]
            if self.raw_segments is not None:
                self.save()
            return self.marks_view()

    def replace_all(self, find: str, by: str, case: bool, whole_word: bool) -> int:
        """Remplace partout (texte seul et texte avec intervenants) ; le dernier remplacement peut être annulé."""
        from dataclasses import replace
        from .documents import motif, remplacer
        if not find.strip():
            raise ServiceError("Indiquez le texte à rechercher.", 422)
        with self._lock:
            self._editable("raw")
            if self.diar.running:
                raise ServiceError("Attendez la fin de l'identification des intervenants.", 409)
            m = motif(find, case, whole_word)
            avant = (list(self.raw_segments or []), list(self.diarized_segments) if self.diarized_segments is not None else None)
            total = 0

            def appliquer(segs: list[TranscriptSegment]) -> tuple[list[TranscriptSegment], int]:
                out, n = [], 0
                for x in segs:
                    texte, k = remplacer(x.text, m, by)
                    texte = " ".join(texte.split())
                    if k and texte:
                        out.append(replace(x, text=texte, words=()))
                        n += k
                    else:
                        out.append(x)
                return out, n

            self.raw_segments, total = appliquer(self.raw_segments or [])
            if self.diarized_segments is not None:
                self.diarized_segments, n = appliquer(self.diarized_segments)
                total = max(total, n)
            if total:
                self._annulables.append(("le remplacement", *avant))
                del self._annulables[:-20]
                self.save()
            return total

    def docx(self) -> tuple[bytes, str]:
        from .documents import segments_to_docx
        if not self.finished:
            raise ServiceError("La session n'est pas terminée.", 409)
        segs = self.named(self.diarized_segments) if self.diarized_segments is not None else (self.raw_segments or [])
        titre = self.title or self.default_title()
        infos = [self.started.replace("T", " à ")[:-3].replace("-", "/") if self.started else "",
                 f"durée {timestamp(self.live.duration)}"]
        noms = sorted({x.speaker for x in segs if x.speaker})
        if noms:
            infos.append(f"intervenants : {', '.join(noms)}")
        return segments_to_docx(segs, titre, " · ".join(i for i in infos if i), self.marks_view()), titre

    def default_title(self) -> str:
        nom = getattr(self.live, "display_name", None)
        if nom:
            return str(nom)
        j, h = self.stamp.split("_")[0], self.stamp.split("_")[1]
        return f"Enregistrement du {j[8:10]}/{j[5:7]}/{j[:4]} à {h[:5].replace('-', ':')}"

    def waveform(self, n: int = 240) -> dict[str, Any]:
        from .documents import forme_onde
        wav = self.live.wav_path
        if not self.finished or not wav.is_file():
            raise ServiceError("Pas d'enregistrement audio pour cette session.", 404)
        cle = wav.stat().st_mtime
        if not self._onde or self._onde[0] != cle or len(self._onde[1]) != n:
            peaks, duree = forme_onde(wav, n)
            self._onde = (cle, peaks, duree)
        return {"peaks": self._onde[1], "duration": round(self._onde[2], 2)}

    def speakers(self) -> list[dict[str, Any]]:
        if self.diarized_segments is None:
            return []
        compte: dict[str, float] = {}
        for s in self.diarized_segments:
            if s.speaker:
                compte[s.speaker] = compte.get(s.speaker, 0.0) + (s.end - s.start)
        return [{"label": l, "name": self.speaker_names.get(l, ""), "seconds": round(t)}
                for l, t in sorted(compte.items())]

    def _discard_wav_if_unwanted(self) -> None:
        """« Conserver le WAV » décoché : l'enregistrement n'est gardé que le temps dont la diarisation a besoin."""
        if not self.params.save_audio:
            self.live.wav_path.unlink(missing_ok=True)

    # -- diarisation ---------------------------------------------------------------------------------------------

    def start_diarization(self, model_path: str, speakers: int = 0) -> None:
        with self._lock:
            if self.diar.running:
                raise ServiceError("Une diarisation est déjà en cours pour cette session.", 409)
            if not self.live.wav_path.is_file():
                raise ServiceError("L'enregistrement WAV de cette session n'existe plus : diarisation impossible.", 409)
            model = _validate_pipeline(model_path)
            job = self.diar
            job.status, job.error, job.fraction, job.phase = "RUNNING", "", None, "préparation"
            job.thread = threading.Thread(target=self._diarize_worker, args=(model, speakers), name="diarization", daemon=True)
            job.thread.start()

    def _diarize_worker(self, model: str, speakers: int) -> None:
        job = self.diar
        try:
            labelled = _diarize(self.live.wav_path, list(self.raw_segments or self.live.segments()), model, speakers, job)
            with self._lock:
                self.diarized_segments = list(labelled)
                self.speaker_names = {}  # nouvelle identification : les étiquettes peuvent avoir changé
                self.save()
            job.status = "DONE"
            self._discard_wav_if_unwanted()
        except Exception as exc:
            log.exception("Diarisation")
            job.status, job.error = "ERROR", f"{type(exc).__name__}: {exc}"

    # -- état renvoyé à l'interface ------------------------------------------------------------------------------

    def files(self) -> dict[str, bool]:
        def ok(p: Path | None) -> bool:
            return bool(p and p.is_file())
        return {"wav": self.live.wav_path.is_file(), "raw_txt": ok(self.raw_txt), "raw_srt": ok(self.raw_srt),
                "diarized_txt": ok(self.diar_txt), "diarized_srt": ok(self.diar_srt)}

    def provider_info(self) -> dict[str, str]:
        p = self.provider
        if p is None:
            return {"engine": "Session rouverte depuis l'historique"}
        if not hasattr(p, "model"):
            return {"engine": "Simulation"}
        return {"engine": "faster-whisper", "faster_whisper": getattr(p, "faster_whisper_version", ""),
                "ctranslate2": getattr(p, "ctranslate2_version", ""),
                "compute": f"{getattr(p, 'device', '?').upper()} · {getattr(p, 'compute_type', '?')}",
                "fallback": getattr(p, "acceleration_fallback", None) or ""}

    def state(self, after: int = 0) -> dict[str, Any]:
        live = self.live
        segments = live.segments()
        start_index = after if 0 <= after <= len(segments) else 0   # le client en sait trop : il repart de zéro
        stats = live.stats
        return {
            "active": True, "id": self.stamp, "kind": getattr(live, "kind", "live"),
            "file": live.progress_info() if hasattr(live, "progress_info") else None, "status": live.status, "paused": live.is_paused,
            "stopping": live.stop_requested, "finalized": self.finished,
            "duration": round(live.duration, 1), "queue": live.queue_size,
            "stats": {"chunks": stats.chunks_processed, "last_latency": round(stats.last_latency, 2),
                      "last_chunk_duration": round(stats.last_chunk_duration, 2), "realtime_ratio": round(stats.realtime_ratio, 2),
                      "average_realtime_ratio": round(stats.average_realtime_ratio, 2),
                      "duplicate_words_removed": stats.duplicate_words_removed},
            "error": stats.last_error, "provider": self.provider_info(),
            "from": start_index, "total": len(segments),
            "segments": [segment_to_dict(s) for s in segments[start_index:]],
            "diarization": {**self.diar.as_dict(), "wanted": self.diar_wanted},
            "files": self.files() if self.finished else {},
            "session_dir": str(live.session_dir), "recovery_copy": str(live.cache.path),
            "save_audio": self.params.save_audio,
            "speakers": self.speakers() if self.finished else [],
            "archived": isinstance(live, ArchivedLive),
            "title": self.title, "default_title": self.default_title(), "started": self.started,
            "marks": self.marks_view(), "can_undo": bool(self._annulables),
            "undo_label": self._annulables[-1][0] if self._annulables else "",
        }

    def transcript(self, variant: str) -> list[dict[str, Any]]:
        if variant == "diarized":
            if self.diarized_segments is None:
                raise ServiceError("La transcription avec intervenants n'est pas encore prête.", 404)
            segs = self.named(self.diarized_segments)
        else:
            segs = self.raw_segments if self.raw_segments is not None else self.live.segments()
        return [segment_to_dict(s, words=True) for s in segs]

    def file_path(self, kind: str) -> Path:
        mapping = {"wav": self.live.wav_path, "raw_txt": self.raw_txt, "raw_srt": self.raw_srt,
                   "diarized_txt": self.diar_txt, "diarized_srt": self.diar_srt}
        path = mapping.get(kind)
        if not path or not path.is_file():
            raise ServiceError("Ce fichier n'est pas (ou plus) disponible.", 404)
        return path


SESSION_FILE = "session.json"


def _write(path: Path, text: str) -> None:
    """Écriture atomique : un export n'est jamais à moitié écrit, même en cas de plantage."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class ArchivedLive:
    """Une session passée, relue sur le disque : terminée, avec la même interface qu'une session live."""

    def __init__(self, session_dir: Path, fiche: dict[str, Any]):
        from .session import SessionStats
        self.session_dir = session_dir
        self.kind = fiche.get("kind") or "live"
        self.display_name = fiche.get("name")
        self.duration = float(fiche.get("duration") or 0)
        self.wav_path = session_dir / f"recording_{session_dir.name}.wav"
        self.stats = SessionStats(last_error=str(fiche.get("error") or ""))
        self.cache = type("Copie", (), {"path": app_data_dir() / "cache" / f"transcript_{session_dir.name}.txt"})()
        self.status, self.is_paused, self.stop_requested, self.is_finalized, self.queue_size = "STOPPED", False, False, True, 0

    def segments(self) -> list[TranscriptSegment]:
        return []

    def progress_info(self) -> dict[str, Any] | None:
        if self.kind != "file":
            return None
        return {"name": self.display_name, "phase": "done", "fraction": 1.0, "eta": None, "media_duration": self.duration}


def _lire_segments(path: Path) -> list[TranscriptSegment] | None:
    try:
        return [segment_from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def sessions_dir() -> Path:
    return app_data_dir() / "sessions"


def open_folder(path: Path) -> None:
    """Ouvre le dossier dans l'Explorateur (Finder sur Mac) : le serveur tourne sur le PC de la personne."""
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _clean_path(raw: str) -> Path:
    return Path((raw or "").strip().strip('"')).expanduser()


# --- Fichiers envoyés par le navigateur ---------------------------------------------------------------------
# Le navigateur et le serveur sont sur le même PC : l'envoi est une simple copie locale, rien ne passe par le réseau.

_UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{16,64}(\.[a-z0-9]{1,8})?")
UPLOAD_MAX_AGE = 24 * 3600


def uploads_dir() -> Path:
    return app_data_dir() / "uploads"


def new_upload(name: str) -> tuple[str, Path]:
    """Identifiant et chemin d'un nouveau fichier envoyé ; nettoie au passage les envois abandonnés de plus d'un jour."""
    folder = uploads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    limite = time.time() - UPLOAD_MAX_AGE
    for old in folder.iterdir():
        try:
            if old.stat().st_mtime < limite:
                old.unlink()
        except OSError:
            pass
    suffix = Path(name).suffix.lower()
    suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""
    upload_id = secrets.token_urlsafe(18) + suffix
    (folder / f"{upload_id}.name").write_text(Path(name).name[:200] or "fichier", encoding="utf-8")
    return upload_id, folder / upload_id


def uploaded_file(upload_id: str) -> Path:
    if not _UPLOAD_ID.fullmatch(upload_id or ""):
        raise ServiceError("Envoi inconnu.", 404)
    path = uploads_dir() / upload_id
    if not path.is_file():
        raise ServiceError("Le fichier envoyé n'est plus disponible : choisissez-le à nouveau.", 404)
    return path


def upload_name(upload_id: str) -> str:
    try:
        return (uploads_dir() / f"{upload_id}.name").read_text(encoding="utf-8").strip() or upload_id
    except OSError:
        return upload_id


# --- Modèle de transcription gardé en mémoire ---------------------------------------------------------------

class ModeleCharge:
    """Un seul modèle Whisper en mémoire, chargé à l'avance et réutilisé d'une session à l'autre.
    La clé (dossier, accélération) change : l'ancien modèle est libéré et le nouveau chargé."""

    def __init__(self) -> None:
        self.cle: tuple[str, str] | None = None
        self.provider: Any = None
        self.etat, self.message = "idle", ""
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def charger(self, cle: tuple[str, str]) -> None:
        with self._lock:
            if self.cle == cle and self.etat in ("loading", "ready"):
                return
            self.cle, self.provider, self.etat, self.message = cle, None, "loading", ""
            self._thread = threading.Thread(target=self._charger, args=(cle,), name="prechargement-modele", daemon=True)
            self._thread.start()

    def _charger(self, cle: tuple[str, str]) -> None:
        from .transcription.whisper import LocalWhisperProvider
        try:
            provider = LocalWhisperProvider(cle[0], acceleration=cle[1])
            erreur = ""
        except Exception as exc:
            provider, erreur = None, str(exc)
            log.warning("Préchargement du modèle : %s", exc)
        with self._lock:
            if self.cle != cle:  # réglages changés entre-temps : ce chargement ne sert plus
                return
            self.provider, self.etat, self.message = provider, ("ready" if provider else "error"), erreur

    def obtenir(self, cle: tuple[str, str]) -> Any:
        """Le modèle préchargé (en attendant la fin de son chargement), ou un nouveau chargé maintenant."""
        self.charger(cle)
        t = self._thread
        if t:
            t.join()
        with self._lock:
            if self.cle == cle and self.provider is not None:
                return self.provider
            message = self.message or "Le modèle n'a pas pu être chargé."
            self.cle, self.etat = None, "idle"  # le prochain essai recharge
        raise RuntimeError(message)

    def as_dict(self) -> dict[str, Any]:
        p = self.provider
        return {"state": self.etat, "message": self.message,
                "device": f"{getattr(p, 'device', '?').upper()} · {getattr(p, 'compute_type', '?')}" if p else ""}


# --- Gestionnaire --------------------------------------------------------------------------------------------

class Manager:
    def __init__(self) -> None:
        self.current: ActiveSession | None = None
        self.preview = Apercu()
        self.modele = ModeleCharge()
        self._index: dict[str, tuple] = {}   # « Mes transcriptions » : fiche et texte de chaque session, par empreinte
        self._lock = threading.RLock()

    # -- sessions ------------------------------------------------------------------------------------------------

    def _new_stamp(self) -> str:
        base = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        stamp, n = base, 1
        while (app_data_dir() / "sessions" / stamp).exists():  # deux départs dans la même seconde
            n += 1
            stamp = f"{base}-{n}"
        return stamp

    @staticmethod
    def _chemin_modele(model_path: str) -> str:
        """Dossier du modèle : celui choisi sur ce poste, sinon celui de l'équipe (Studio Dock) ; vérifié."""
        from .transcription.whisper import validate_ctranslate2_model
        if not model_path.strip():
            equipe = team_model()
            if equipe is None:
                raise ServiceError("Aucun modèle de transcription : Studio Dock n'en a pas installé sur ce poste "
                                   "(Réglages › Modèles d'IA), et aucun dossier n'est indiqué ici.", 422)
            model_path = equipe.path
        check = validate_ctranslate2_model(model_path)
        if not check.valid:
            detail = f" Manquants : {', '.join(check.missing)}." if check.missing else ""
            raise ServiceError(check.message + detail, 422)
        return str(check.path)

    def preload(self, model_path: str, acceleration: str) -> dict[str, Any]:
        """Charge le modèle en arrière-plan dès l'ouverture de la page : « Démarrer » part ensuite tout de suite."""
        chemin = self._chemin_modele(model_path)
        self.modele.charger((chemin, acceleration))
        return self.modele.as_dict()

    def _provider(self, p: StartParams):
        if p.engine == "mock":
            return MockProvider()
        p.model_path = self._chemin_modele(p.model_path)
        try:
            provider = self.modele.obtenir((p.model_path, p.acceleration))
        except (ValueError, RuntimeError) as exc:
            raise ServiceError(str(exc), 422) from exc
        provider.configure(p.vad_filter, p.glossary)
        return provider

    def _sources(self, p: StartParams) -> dict[str, Any]:
        """Les sources séparées : « voix » (micro) et / ou « autre » (application ou tout le son du PC)."""
        rate, block = CONFIG.sample_rate, CONFIG.block_ms
        out: dict[str, Any] = {}
        if p.source in ("microphone", "mixed"):
            if p.input_device is None:
                raise ServiceError("Aucun microphone sélectionné.", 422)
            out["voix"] = MicrophoneSource(device=p.input_device, sample_rate=rate, channels=1, block_ms=block)
        if p.source in ("system", "mixed"):
            out["autre"] = self._app_source(p.app, rate, block) if p.app.strip() else \
                SystemAudioSource(p.output_device or None, sample_rate=rate, channels=1, block_ms=block)
        return out

    def preview_start(self, p: StartParams) -> dict[str, Any]:
        """Ouvre la ou les sources sans rien enregistrer, pour vérifier qu'on entend bien avant de démarrer."""
        with self._lock:
            if self.current and not self.current.finished:
                raise ServiceError("Une session est en cours.", 409)
            if p.source not in ("microphone", "system", "mixed"):
                raise ServiceError("Source inconnue.", 422)
            cle = (p.source, p.input_device, p.output_device, p.app)
            try:
                return self.preview.demarrer(cle, lambda: self._sources(p))
            except OSError as exc:
                raise ServiceError(f"Impossible d'ouvrir la source audio : {exc}", 422) from exc

    def _source(self, p: StartParams):
        sources = self._sources(p)
        if len(sources) == 1:
            return next(iter(sources.values()))
        return MixedAudioSource(sources["voix"], sources["autre"], sample_rate=CONFIG.sample_rate, block_ms=CONFIG.block_ms)

    @staticmethod
    def _app_source(exe: str, rate: int, block: int):
        """Son d'une seule application, retrouvée par son programme parmi celles ouvertes maintenant."""
        from .audio import app_audio
        ok, raison = app_audio.app_capture_status()
        if not ok:
            raise ServiceError(raison, 422)
        app = app_audio.choisir(app_audio.list_audio_apps(), exe)
        if app is None:
            nom = app_audio.nom_lisible(exe.lower().strip())
            raise ServiceError(f"{nom} n'est pas ouvert, ou n'a encore produit aucun son. Lancez la réunion (ou la vidéo), "
                               "puis réessayez ; vous pouvez aussi choisir « Tout le son de l'ordinateur ».", 422)
        return app_audio.ProcessLoopbackSource(app.pid, app.name, sample_rate=rate, block_ms=block)

    def _check_free(self) -> None:
        if self.current and not self.current.finished:
            raise ServiceError("Une session est déjà en cours.", 409)
        if self.current and self.current.diar.running:
            raise ServiceError("Attendez la fin de la diarisation avant de commencer une nouvelle session.", 409)

    @staticmethod
    def _diarization_choice(p: StartParams) -> tuple[bool, str, str]:
        """(à lancer, dossier du pipeline, note affichée si elle ne sera pas lancée)."""
        if not p.diarization:
            return False, "", ""
        from .diarization import validate_diarization_model
        ok, detail = validate_diarization_model(p.diarization_model_path)
        return (True, detail, "") if ok else (False, "", f"Diarisation non lancée : {detail}")

    def _launch(self, live: Any, stamp: str, p: StartParams, provider: Any) -> dict[str, Any]:
        wanted, model, note = self._diarization_choice(p)
        active = ActiveSession(live, stamp, p, provider, note)
        active.diar_wanted, active.diar_model_path = wanted, model
        try:
            live.start()
        except OSError as exc:
            raise ServiceError(f"Impossible d'ouvrir la source audio : {exc}", 422) from exc
        active.watch()
        self.current = active
        return active.state()

    def start(self, p: StartParams) -> dict[str, Any]:
        with self._lock:
            self._check_free()
            if p.source not in ("microphone", "system", "mixed") or p.engine not in ("local", "mock"):
                raise ServiceError("Source ou moteur inconnu.", 422)
            provider = self._provider(p)
            self.preview.arreter()  # le micro ne doit pas être ouvert deux fois
            source = self._source(p)
            stamp = self._new_stamp()
            live = LiveSession(source, provider, p.chunk_seconds, p.language, p.save_audio,
                               overlap_seconds=p.overlap_seconds, session_id=stamp)
            return self._launch(live, stamp, p, provider)

    def start_file(self, p: StartParams, upload_id: str = "", path: str = "") -> dict[str, Any]:
        """Transcription d'un fichier : envoyé par le navigateur (upload_id) ou déjà sur ce PC (path, jamais modifié)."""
        with self._lock:
            self._check_free()
            if upload_id:
                source, name, temporary = uploaded_file(upload_id), upload_name(upload_id), True
            else:
                source, temporary = _clean_path(path), False
                if not str(path).strip():
                    raise ServiceError("Choisissez un fichier.", 422)
                if not source.is_file():
                    raise ServiceError(f"Fichier introuvable : {source}", 422)
                name = source.name
            provider = self._provider(p)
            stamp = self._new_stamp()
            live = FileTranscription(source, provider, p.language, stamp, p.save_audio, display_name=name,
                                     delete_source=temporary)
            return self._launch(live, stamp, p, provider)

    def _need(self) -> ActiveSession:
        if not self.current:
            raise ServiceError("Aucune session.", 404)
        return self.current

    def state(self, after: int = 0) -> dict[str, Any]:
        s = self.current
        return s.state(after) if s else {"active": False}

    def pause(self) -> dict[str, Any]:
        s = self._need()
        if s.finished or s.live.stop_requested:
            raise ServiceError("La session est terminée.", 409)
        s.live.pause()
        return s.state()

    def resume(self) -> dict[str, Any]:
        s = self._need()
        if s.finished or s.live.stop_requested:
            raise ServiceError("La session est terminée.", 409)
        s.live.resume()
        return s.state()

    def stop(self) -> dict[str, Any]:
        s = self._need()
        if not s.live.stop_requested:
            try:
                s.live.stop()
            except RuntimeError as exc:
                raise ServiceError(str(exc), 500) from exc
        return s.state()

    def discard(self) -> None:
        with self._lock:
            s = self.current
            if not s:
                return
            if not s.finished:
                raise ServiceError("La session n'est pas terminée.", 409)
            if s.diar.running:
                raise ServiceError("Attendez la fin de la diarisation avant de commencer une nouvelle session.", 409)
            self.current = None

    # -- historique ------------------------------------------------------------------------------------------------

    def _fiche_indexee(self, d: Path) -> tuple[dict[str, Any], str] | None:
        """Fiche d'une session pour « Mes transcriptions » et son texte complet, relus seulement s'ils ont changé :
        la liste et la recherche restent rapides avec des centaines de sessions."""
        from .documents import duree_wav
        wav = d / f"recording_{d.name}.wav"
        copie = app_data_dir() / "cache" / f"transcript_{d.name}.txt"
        fichiers = (d / SESSION_FILE, d / "transcript_raw.json", d / "transcript_diarized.json", wav, copie)

        def empreinte(f: Path) -> tuple[float, int] | None:
            try:
                st = f.stat()
                return st.st_mtime, st.st_size
            except OSError:
                return None
        signature = tuple(empreinte(f) for f in fichiers)
        cache = self._index.get(d.name)
        if cache and cache[0] == signature:
            return cache[1], cache[2]

        taille_audio = signature[3][1] if signature[3] else 0
        taille = 0
        for f in d.iterdir():
            try:
                taille += f.stat().st_size
            except OSError:
                pass
        try:
            fiche = json.loads((d / SESSION_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fiche = None
        if fiche is None:
            if not wav.is_file() and not copie.is_file():
                return None
            texte = copie.read_text(encoding="utf-8", errors="replace") if copie.is_file() else ""
            texte = " ".join(re.sub(r"\[\d+:\d\d:\d\d\]\s?", " ", texte).split())
            base = {"id": d.name, "interrupted": True, "kind": "live", "name": None, "title": "",
                    "duration": duree_wav(wav) if wav.is_file() else None, "segments": None,
                    "diarized": False, "audio": wav.is_file(), "recoverable": copie.is_file(),
                    "speakers": [], "unnamed": 0, "marks": 0, "size": taille, "audio_size": taille_audio}
        else:
            raw = _lire_segments(d / "transcript_raw.json") or []
            diar = _lire_segments(d / "transcript_diarized.json")
            texte = " ".join(x.text for x in raw)
            noms = {str(k): str(v) for k, v in (fiche.get("speaker_names") or {}).items()}
            etiquettes = sorted({x.speaker for x in diar or [] if x.speaker})
            base = {"id": d.name, "interrupted": False, "kind": fiche.get("kind"), "name": fiche.get("name"),
                    "title": str(fiche.get("title") or ""), "started": fiche.get("started"), "duration": fiche.get("duration"),
                    "segments": fiche.get("segments"), "diarized": bool(fiche.get("diarized")),
                    "audio": wav.is_file(), "error": fiche.get("error") or "",
                    "speakers": [noms[e] for e in etiquettes if e in noms],
                    "unnamed": sum(1 for e in etiquettes if e not in noms),
                    "marks": len(fiche.get("marks") or []), "size": taille, "audio_size": taille_audio}
        self._index[d.name] = (signature, base, texte)
        return base, texte

    def history(self, q: str = "") -> list[dict[str, Any]]:
        """Sessions enregistrées, de la plus récente à la plus ancienne. Une session sans fiche (application fermée
        pendant l'enregistrement) apparaît comme interrompue : son WAV et sa copie de récupération restent.
        Avec q : seulement celles dont le texte ou le titre contient q (accents et majuscules ignorés), avec l'extrait."""
        from .documents import compter, extrait
        courant = self.current.stamp if self.current else None
        try:
            dossiers = sorted((d for d in sessions_dir().iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
        except OSError:
            return []
        presents = {d.name for d in dossiers}
        for ancien in set(self._index) - presents:
            self._index.pop(ancien, None)
        sorties = []
        for d in dossiers:
            lu = self._fiche_indexee(d)
            if lu is None:
                continue
            base, texte = lu
            if d.name == courant and (base["interrupted"] or not self.current.finished):
                continue  # session en cours : elle est sur la page principale
            ex = extrait(texte, q)
            n = compter(texte, q) + compter(base["title"], q)
            if q and not n:
                continue
            sorties.append({**base, "current": d.name == courant, "excerpt": ex or extrait(texte), "matches": n})
        return sorties

    def delete_audio(self, session_id: str) -> int:
        """Supprime l'enregistrement audio d'une session et garde son texte ; renvoie la place libérée (octets)."""
        with self._lock:
            if self.current and self.current.stamp == session_id and (not self.current.finished or self.current.diar.running):
                raise ServiceError("Cette session est en cours.", 409)
            d = self._session_dir(session_id)
            if not (d / SESSION_FILE).is_file():
                raise ServiceError("Récupérez d'abord le texte de cette session : son audio est sa seule sauvegarde.", 409)
            wav = d / f"recording_{session_id}.wav"
            try:
                taille = wav.stat().st_size
            except OSError:
                return 0
            wav.unlink(missing_ok=True)
            if self.current and self.current.stamp == session_id:
                self.current._onde = None
            return taille

    def purge_audio(self, days: int) -> dict[str, int]:
        """Supprime l'audio des sessions de plus de `days` jours (le texte, les noms et les titres restent)."""
        limite = datetime.now().timestamp() - days * 86400
        liberes, nombre = 0, 0
        for s in self.history():
            if s["interrupted"] or not s["audio"] or s["current"]:
                continue
            try:
                debut = datetime.strptime(s["id"][:19], "%Y-%m-%d_%H-%M-%S").timestamp()
            except ValueError:
                continue
            if debut < limite:
                liberes += self.delete_audio(s["id"])
                nombre += 1
        return {"freed": liberes, "count": nombre}

    def set_history_title(self, session_id: str, title: str) -> dict[str, Any]:
        """Renomme une session depuis « Mes transcriptions » (ou la session ouverte, si c'est elle)."""
        with self._lock:
            if self.current and self.current.stamp == session_id:
                return {"title": self.current.set_title(title)}
            d = self._session_dir(session_id)
            chemin = d / SESSION_FILE
            try:
                fiche = json.loads(chemin.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ServiceError("Récupérez d'abord le texte de cette session.", 409) from exc
            fiche["title"] = " ".join((title or "").split())[:120]
            _write(chemin, json.dumps(fiche, ensure_ascii=False, indent=2))
            return {"title": fiche["title"]}

    def recover(self, session_id: str) -> dict[str, Any]:
        """Session interrompue : reconstruit sa fiche et son texte depuis la copie de récupération, puis la rouvre."""
        from .documents import duree_wav, lire_copie
        with self._lock:
            self._check_free()
            d = self._session_dir(session_id)
            if (d / SESSION_FILE).is_file():
                return self.reopen(session_id)
            copie = app_data_dir() / "cache" / f"transcript_{session_id}.txt"
            if not copie.is_file():
                raise ServiceError("Aucune copie du texte pour cette session : seul son audio a été conservé.", 409)
            wav = d / f"recording_{session_id}.wav"
            duree = duree_wav(wav) if wav.is_file() else None
            segments = lire_copie(copie.read_text(encoding="utf-8", errors="replace"), duree)
            if not segments:
                raise ServiceError("La copie du texte de cette session est vide.", 409)
            duree = duree or segments[-1].end
            _write(d / "transcript_raw.json", json.dumps([segment_to_dict(x, True) for x in segments], ensure_ascii=False))
            stamp = session_id
            _write(d / f"transcript_{stamp}_raw.txt", segments_to_txt(segments))
            _write(d / f"transcript_{stamp}_raw.srt", segments_to_srt(segments))
            j, h = stamp.split("_")[0], stamp.split("_")[1]
            fiche = {"format": 1, "id": stamp, "kind": "live", "title": "", "marks": [], "name": None,
                     "started": f"{j}T{h[:8].replace('-', ':')}", "duration": round(duree, 1), "language": "fr",
                     "segments": len(segments), "diarized": False, "speaker_names": {},
                     "error": "Texte récupéré après une fermeture inattendue : les dernières secondes peuvent manquer."}
            _write(d / SESSION_FILE, json.dumps(fiche, ensure_ascii=False, indent=2))
            return self.reopen(session_id)

    def mark(self, label: str = "") -> list[dict[str, Any]]:
        return self._need().add_mark(label)

    def _session_dir(self, session_id: str) -> Path:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}(-[0-9]+)?", session_id or ""):
            raise ServiceError("Session inconnue.", 404)
        d = sessions_dir() / session_id
        if not d.is_dir():
            raise ServiceError("Cette session n'existe plus.", 404)
        return d

    def reopen(self, session_id: str) -> dict[str, Any]:
        """Rouvre une session passée sur la page principale (exports, lecteur, corrections, intervenants)."""
        with self._lock:
            if self.current and self.current.stamp == session_id:
                return self.current.state()
            self._check_free()
            d = self._session_dir(session_id)
            try:
                fiche = json.loads((d / SESSION_FILE).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ServiceError("Session interrompue : seul son dossier peut être ouvert.", 409) from exc
            raw = _lire_segments(d / "transcript_raw.json")
            if raw is None:
                raise ServiceError("Le texte de cette session est illisible.", 409)
            params = StartParams(language=str(fiche.get("language") or "fr"), save_audio=True, diarization=False)
            active = ActiveSession(ArchivedLive(d, fiche), session_id, params, MockProvider())
            active.provider = None
            active.started = fiche.get("started") or active.started
            active.raw_segments = raw
            active.diarized_segments = _lire_segments(d / "transcript_diarized.json")
            active.speaker_names = {str(k): str(v) for k, v in (fiche.get("speaker_names") or {}).items()}
            active.title = str(fiche.get("title") or "")
            active.marks = [{"t": float(m["t"]), "label": str(m.get("label") or "") if m.get("named") else ""}
                            for m in fiche.get("marks") or [] if isinstance(m, dict) and "t" in m]
            if active.diarized_segments is not None:
                active.diar.status = "DONE"
            for nom, attribut in (("raw.txt", "raw_txt"), ("raw.srt", "raw_srt"), ("diarized.txt", "diar_txt"),
                                  ("diarized.srt", "diar_srt")):
                chemin = d / f"transcript_{session_id}_{nom}"
                setattr(active, attribut, chemin if chemin.is_file() else None)
            active._exports_done.set()
            self.current = active
            return active.state()

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            if self.current and self.current.stamp == session_id:
                if not self.current.finished or self.current.diar.running:
                    raise ServiceError("Cette session est en cours.", 409)
                self.current = None
            d = self._session_dir(session_id)
            shutil.rmtree(d, ignore_errors=True)
            (app_data_dir() / "cache" / f"transcript_{session_id}.txt").unlink(missing_ok=True)

    def open_session_folder(self, session_id: str | None = None) -> None:
        d = self._session_dir(session_id) if session_id else self._need().live.session_dir
        try:
            open_folder(d)
        except OSError as exc:
            raise ServiceError(f"Impossible d'ouvrir le dossier : {exc}", 500) from exc

    def shutdown(self) -> None:
        """Arrêt propre du serveur : referme le WAV de la session en cours pour qu'il reste lisible."""
        s = self.current
        if s and not s.finished and not s.live.stop_requested:
            try:
                s.live.stop()
            except Exception:
                log.exception("Arrêt de la session à la fermeture")


def team_model():
    """Modèle de transcription installé par Studio Dock pour l'équipe (studiodock_ia.transcription()), ou None."""
    try:
        import studiodock_ia
        return studiodock_ia.transcription()
    except Exception:  # contrat absent ou fichier illisible : comme s'il n'y en avait pas
        return None


manager = Manager()

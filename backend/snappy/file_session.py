"""Transcription d'un fichier audio ou vidéo, avec la même interface que la session live (LiveSession).

Étapes : lecture du fichier (n'importe quel format) → WAV 16 kHz dans le dossier de la session → transcription par
fenêtres d'environ 10 minutes. Pause, reprise et arrêt agissent entre deux segments ; un arrêt garde le texte déjà
transcrit. Ensuite, le reste de l'app (exports, lecteur, diarisation) traite la session comme une session live.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from .cache import TranscriptCache
from .media import SAMPLE_RATE, DecodeError, decode_to_wav, iter_windows
from .models import TranscriptSegment
from .paths import app_data_dir
from .session import SessionStats

log = logging.getLogger(__name__)

FALLBACK_PIECE_SECONDS = 5  # moteurs sans transcription en flux (simulation) : morceaux de 5 s


class FileTranscription:
    kind = "file"

    def __init__(self, source: Path, provider: Any, language: str, session_id: str, save_audio: bool = True,
                 display_name: str = "", delete_source: bool = False):
        self.source, self.provider, self.language = Path(source), provider, language
        self.display_name = display_name or self.source.name
        self.delete_source = delete_source  # copie envoyée par le navigateur : supprimée une fois lue
        self.save_audio = save_audio
        self.sample_rate = SAMPLE_RATE
        self.session_id = session_id
        self.stats = SessionStats()
        self.session_dir = app_data_dir() / "sessions" / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.wav_path = self.session_dir / f"recording_{session_id}.wav"
        self.cache = TranscriptCache(session_id)
        self.cache.write([])

        self._segments: list[TranscriptSegment] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "DECODING"
        self.phase = "decoding"            # decoding | transcribing | done
        self.fraction: float | None = 0.0  # avancement de l'étape en cours (None : inconnu)
        self._phase_started = time.monotonic()
        self._paused_for = 0.0             # temps passé en pause pendant l'étape : exclu de l'estimation
        self.media_duration: float | None = None
        self.audio_seconds = 0.0

    # --- interface commune avec LiveSession -----------------------------------------------------------------

    @property
    def status(self) -> str:
        with self._lock:
            status = self._status
        if self.is_finalized:
            return "ERROR" if status == "ERROR" else "STOPPED"
        return "PAUSED" if self._pause.is_set() else status

    @property
    def duration(self) -> float:
        return self.audio_seconds

    @property
    def queue_size(self) -> int:
        return 0

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set() and not self.is_finalized

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    @property
    def is_finalized(self) -> bool:
        return self._thread is not None and not self._thread.is_alive()

    def segments(self) -> list[TranscriptSegment]:
        with self._lock:
            return list(self._segments)

    def start(self) -> None:
        if not self.source.is_file():
            raise FileNotFoundError(f"Fichier introuvable : {self.source}")
        self._thread = threading.Thread(target=self._run, name="file-transcription", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if not self._stop.is_set():
            self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def stop(self) -> None:
        """Arrêt demandé : le texte déjà transcrit est conservé et exporté."""
        self._stop.set()
        self._pause.clear()

    # --- avancement ------------------------------------------------------------------------------------------

    def progress_info(self) -> dict[str, Any]:
        eta = None
        if self.fraction and 0.02 < self.fraction < 1 and not self.is_paused:
            elapsed = time.monotonic() - self._phase_started - self._paused_for
            eta = round(elapsed / self.fraction - elapsed, 1)
        return {"name": self.display_name, "phase": self.phase,
                "fraction": None if self.fraction is None else round(self.fraction, 4), "eta": eta,
                "media_duration": None if self.media_duration is None else round(self.media_duration, 1)}

    def _set_phase(self, phase: str, status: str) -> None:
        self.phase, self.fraction = phase, 0.0
        self._phase_started, self._paused_for = time.monotonic(), 0.0
        with self._lock:
            self._status = status

    def _checkpoint(self) -> bool:
        """Attend tant que la session est en pause ; renvoie True si l'arrêt est demandé."""
        if self._pause.is_set():
            debut = time.monotonic()
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.1)
            self._paused_for += time.monotonic() - debut
        return self._stop.is_set()

    # --- travail ---------------------------------------------------------------------------------------------

    def _run(self) -> None:
        try:
            seconds, announced = decode_to_wav(self.source, self.wav_path, self._on_decode_progress, self._checkpoint)
            self.audio_seconds, self.media_duration = seconds, announced or seconds
            if not self._stop.is_set():
                self._transcribe_all()
            self.fraction = 1.0 if not self._stop.is_set() else self.fraction
            self.phase = "done"
        except DecodeError as exc:
            self._fail(str(exc))
        except Exception as exc:
            log.exception("Transcription du fichier")
            self._fail(f"Transcription : {type(exc).__name__}: {exc}")
        finally:
            if self.delete_source:
                self.source.unlink(missing_ok=True)
                self.source.with_name(self.source.name + ".name").unlink(missing_ok=True)
            try:
                self.cache.write(self.segments())
            except Exception as exc:
                log.warning("Copie de récupération : %s", exc)

    def _fail(self, message: str) -> None:
        self.stats.last_error = message
        with self._lock:
            self._status = "ERROR"

    def _on_decode_progress(self, fraction: float | None, seconds: float) -> None:
        self.fraction, self.audio_seconds = fraction, seconds

    def _transcribe_all(self) -> None:
        self._set_phase("transcribing", "TRANSCRIBING")
        total = max(self.audio_seconds, 0.001)
        last_cache = time.monotonic()
        ratio_sum = 0.0
        for offset, samples in iter_windows(self.wav_path):
            if self._checkpoint():
                return
            debut = time.monotonic()
            for seg in self._stream(samples, offset):
                with self._lock:
                    self._segments.append(seg)
                self.fraction = min(1.0, seg.end / total)
                if time.monotonic() - last_cache > 2:
                    self.cache.write(self.segments())
                    last_cache = time.monotonic()
                if self._checkpoint():
                    return
            duree = samples.size / SAMPLE_RATE
            st = self.stats
            st.chunks_processed += 1
            st.last_latency, st.last_chunk_duration = time.monotonic() - debut, duree
            st.realtime_ratio = st.last_latency / duree if duree else 0.0
            ratio_sum += st.realtime_ratio
            st.average_realtime_ratio = ratio_sum / st.chunks_processed
            self.fraction = min(1.0, (offset + duree) / total)

    def _stream(self, samples: np.ndarray, offset: float):
        if hasattr(self.provider, "transcribe_stream"):
            yield from self.provider.transcribe_stream(samples, offset, self.language)
            return
        piece = FALLBACK_PIECE_SECONDS * SAMPLE_RATE
        for i in range(0, samples.size, piece):
            yield from self.provider.transcribe(samples[i:i + piece].tobytes(), SAMPLE_RATE, offset + i / SAMPLE_RATE, self.language)
            if self._stop.is_set():
                return

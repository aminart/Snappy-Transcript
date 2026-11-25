from __future__ import annotations

import io
import logging
import threading
import time
import wave
from dataclasses import dataclass

from audio.base import AudioSource

logger = logging.getLogger(__name__)


@dataclass
class RecorderStats:
    started_at: float | None = None
    bytes_recorded: int = 0
    blocks_recorded: int = 0
    last_error: str | None = None


class Recorder:
    def __init__(self, source: AudioSource, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2):
        self.source = source
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.stats = RecorderStats()
        self._audio = bytearray()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    @property
    def duration(self) -> float:
        if self.stats.started_at is None:
            return 0.0
        if self.is_recording:
            return time.monotonic() - self.stats.started_at
        frame_count = self.stats.bytes_recorded / (self.sample_width * self.channels)
        return frame_count / self.sample_rate

    def start(self) -> None:
        if self.is_recording:
            return
        self._audio.clear()
        self.stats = RecorderStats(started_at=time.monotonic())
        self._stop_event.clear()
        self.source.start()
        self._thread = threading.Thread(target=self._worker, name="audio-recorder", daemon=True)
        self._thread.start()
        logger.info("Recording started")

    def _worker(self) -> None:
        try:
            while not self._stop_event.is_set():
                chunk = self.source.read_chunk(timeout=0.2)
                if not chunk:
                    continue
                with self._lock:
                    self._audio.extend(chunk)
                    self.stats.bytes_recorded += len(chunk)
                    self.stats.blocks_recorded += 1
        except Exception as exc:
            self.stats.last_error = str(exc)
            logger.exception("Recorder worker failed")
            self._stop_event.set()

    def stop(self) -> bytes:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.source.stop()
        logger.info("Recording stopped")
        return self.to_wav_bytes()

    def to_wav_bytes(self) -> bytes:
        with self._lock:
            pcm = bytes(self._audio)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(self.sample_width)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
        return buffer.getvalue()

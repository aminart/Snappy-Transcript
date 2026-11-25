import os
import tempfile
import wave
from pathlib import Path

from models.transcript import TranscriptSegment
from transcription.base import TranscriptionProvider

class MockProvider(TranscriptionProvider):
    def transcribe(self, pcm: bytes, sample_rate: int, offset: float, language: str) -> list[TranscriptSegment]:
        duration = len(pcm) / (sample_rate * 2)
        return [TranscriptSegment(offset, offset + duration, "[Simulation : audio reçu, pas de transcription réelle]")] if pcm else []

class LocalWhisperProvider(TranscriptionProvider):
    def __init__(self, model_name: str = "tiny", model_dir: str | None = None):
        from faster_whisper import WhisperModel
        # Un modèle doit être préchargé dans le cache, ou téléchargé avec autorisation IT.
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8",
                                  download_root=model_dir or None, local_files_only=True)

    def transcribe(self, pcm: bytes, sample_rate: int, offset: float, language: str) -> list[TranscriptSegment]:
        if not pcm:
            return []
        fd, name = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as raw:
                with wave.open(raw, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(pcm)
            segments, _ = self.model.transcribe(name, language=None if language == "auto" else language,
                                                beam_size=1, vad_filter=False)
            return [TranscriptSegment(offset + s.start, offset + s.end, s.text.strip())
                    for s in segments if s.text.strip()]
        finally:
            Path(name).unlink(missing_ok=True)

from .base import TranscriptionProvider
from ..models import TranscriptSegment

class MockProvider(TranscriptionProvider):
    def transcribe(self, pcm: bytes, sample_rate: int, offset: float, language: str) -> list[TranscriptSegment]:
        duration = len(pcm) / (2 * sample_rate)
        if duration <= 0: return []
        return [TranscriptSegment(offset, offset + duration, f"[MODE TEST — fenêtre {offset:.1f}–{offset + duration:.1f} s, aucune transcription réelle]")]

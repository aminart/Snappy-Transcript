from abc import ABC, abstractmethod
from ..models import TranscriptSegment

class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, pcm: bytes, sample_rate: int, offset: float, language: str) -> list[TranscriptSegment]: ...

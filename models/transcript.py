"""Structures de transcription partagées par le STT, la diarisation, les exports et le lecteur synchronisé."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptWord:
    """Un mot avec son horodatage (en secondes depuis le début de la session)."""
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptSegment:
    """Un segment de transcription ; `words` est vide quand le STT ne fournit pas de timing mot à mot."""
    start: float
    end: float
    text: str
    speaker: str | None = None
    words: tuple[TranscriptWord, ...] = ()

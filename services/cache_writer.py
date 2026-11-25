from __future__ import annotations
import os
from models.transcript import TranscriptSegment
from utils.export import segments_to_txt
from utils.paths import app_data_dir

class TranscriptCache:
    """Crash-resistant local text cache. Each update is atomic (tmp -> replace)."""
    def __init__(self, session_id: str):
        root = app_data_dir() / 'cache'
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f'transcript_{session_id}.txt'
        self.tmp_path = root / f'.transcript_{session_id}.tmp'

    def write(self, segments: list[TranscriptSegment]) -> None:
        text = segments_to_txt(segments)
        self.tmp_path.write_text(text, encoding='utf-8')
        os.replace(self.tmp_path, self.path)

    def mark_final(self) -> None:
        # Keep the cache intentionally: it is a recovery copy, not a temporary lock file.
        pass

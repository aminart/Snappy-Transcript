from .models import TranscriptSegment

def timestamp(seconds: float, srt: bool = False) -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}" if srt else f"{hours:02d}:{minutes:02d}:{secs:02d}"

def segments_to_txt(segments: list[TranscriptSegment]) -> str:
    return '\n'.join(f"[{timestamp(s.start)}] {s.speaker + ': ' if s.speaker else ''}{s.text}" for s in segments) + ('\n' if segments else '')

def segments_to_srt(segments: list[TranscriptSegment]) -> str:
    return '\n\n'.join(f"{i}\n{timestamp(s.start, True)} --> {timestamp(max(s.end, s.start + 0.001), True)}\n{s.speaker + ': ' if s.speaker else ''}{s.text}" for i,s in enumerate(segments,1)) + ('\n' if segments else '')

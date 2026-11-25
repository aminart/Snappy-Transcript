from models.transcript import TranscriptSegment

def timestamp(seconds: float, srt: bool = False) -> str:
    millis = round(max(0, seconds) * 1000)
    h, rem = divmod(millis, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}{',' if srt else '.'}{ms:03}"

def segments_to_txt(segments: list[TranscriptSegment]) -> str:
    return "\n".join(
        f"[{timestamp(s.start).split('.')[0]}] "
        f"{(s.speaker + ': ') if s.speaker else ''}{s.text}"
        for s in segments
    )

def segments_to_srt(segments: list[TranscriptSegment]) -> str:
    return "\n\n".join(
        f"{i}\n{timestamp(s.start, True)} --> {timestamp(s.end, True)}\n"
        f"{(s.speaker + ': ') if s.speaker else ''}{s.text}"
        for i, s in enumerate(segments, 1)
    ) + ("\n" if segments else "")

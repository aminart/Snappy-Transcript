from snappy.models import TranscriptSegment
from snappy.export import segments_to_srt, segments_to_txt, timestamp
from snappy.srt import parse_srt


def test_timestamp_txt_et_srt():
    assert timestamp(3725.5) == "01:02:05"
    assert timestamp(3725.5, srt=True) == "01:02:05,500"
    assert timestamp(-3) == "00:00:00"


def test_txt_avec_et_sans_locuteur():
    segs = [TranscriptSegment(0, 2, "Bonjour"), TranscriptSegment(65, 70, "Salut", "SPEAKER_01")]
    assert segments_to_txt(segs) == "[00:00:00] Bonjour\n[00:01:05] SPEAKER_01: Salut\n"
    assert segments_to_txt([]) == ""


def test_srt_aller_retour_avec_locuteur():
    segs = [TranscriptSegment(0.5, 2.25, "Bonjour tout le monde"), TranscriptSegment(3, 4, "Oui", "SPEAKER_00")]
    relu = parse_srt(segments_to_srt(segs))
    assert [(s.start, s.end, s.text, s.speaker) for s in relu] == [
        (0.5, 2.25, "Bonjour tout le monde", None), (3.0, 4.0, "Oui", "SPEAKER_00")]

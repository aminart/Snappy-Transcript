import time
import wave

from snappy.models import TranscriptSegment, TranscriptWord
from snappy.session import LiveSession
from snappy.transcription.base import TranscriptionProvider
from snappy.transcription.mock import MockProvider

from fakes import BLOC, RATE, SourceFactice


class Lent(TranscriptionProvider):
    def transcribe(self, pcm, sample_rate, offset, language):
        time.sleep(0.4)
        return []


def _attendre(condition, delai=5.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return False


def _session(source, provider=None, chunk=1.0):
    return LiveSession(source, provider or MockProvider(), chunk, "fr", True, overlap_seconds=0.25, session_id="t")


def test_session_complete_ecrit_le_wav_et_transcrit():
    s = _session(SourceFactice(blocs=35))
    s.start()
    assert _attendre(lambda: s.duration >= 3.5)
    s.stop()
    assert _attendre(lambda: s.is_finalized)
    with wave.open(str(s.wav_path)) as w:
        assert w.getnframes() == 35 * RATE // 10 and w.getframerate() == RATE
    assert len(s.segments()) >= 3
    assert s.status == "STOPPED"


def test_stop_reussit_meme_si_la_source_echoue_pendant_l_arret():
    """Régression : l'erreur levée par read_chunk pendant le drain empêchait _capture_done, donc STOP échouait."""
    s = _session(SourceFactice(blocs=15, echec_apres_arret=True))
    s.start()
    assert _attendre(lambda: s.duration >= 1.5)
    s.stop()
    assert _attendre(lambda: s.is_finalized)
    assert s.wav_path.is_file()


def test_echec_au_demarrage_ne_laisse_pas_de_wav_ouvert():
    s = _session(SourceFactice(echec_au_demarrage=True))
    try:
        s.start()
    except OSError:
        pass
    assert s._wav is None


def test_le_statut_pause_survit_a_la_fin_d_un_chunk():
    """Régression : le thread STT remettait « LISTENING » en fin de chunk alors que la session était en pause."""
    s = _session(SourceFactice(blocs=12), Lent())
    s.start()
    assert _attendre(lambda: s.status == "TRANSCRIBING")
    s.pause()
    assert _attendre(lambda: s.stats.chunks_processed >= 1)
    assert s.status == "PAUSED"
    s.resume()
    assert s.status == "LISTENING"
    s.stop()
    assert _attendre(lambda: s.is_finalized)


def _seg(debut, fin, texte, mots=()):
    return TranscriptSegment(debut, fin, texte, words=tuple(TranscriptWord(a, b, t) for a, b, t in mots))


def test_recouvrement_les_mots_repetes_sont_retires_et_le_debut_corrige():
    s = _session(SourceFactice())
    s._merge_result([_seg(0, 5, "on se retrouve demain", [(0, 1, "on"), (1, 2, "se"), (2, 3, "retrouve"), (3, 5, "demain")])])
    s._merge_result([_seg(4.2, 8, "retrouve demain matin", [(4.2, 4.6, "retrouve"), (4.6, 5, "demain"), (6, 8, "matin")])])
    assert [x.text for x in s.segments()] == ["on se retrouve demain", "matin"]
    assert s.segments()[1].start == 6
    assert s.stats.duplicate_words_removed == 2


def test_une_repetition_legitime_a_distance_n_est_pas_supprimee():
    """Régression : « Merci. » dit après un long silence perdait son mot, comparé à un segment vieux de minutes."""
    s = _session(SourceFactice())
    s._merge_result([_seg(0, 2, "D'accord, merci.")])
    s._merge_result([_seg(600, 602, "Merci beaucoup.")])
    assert [x.text for x in s.segments()] == ["D'accord, merci.", "Merci beaucoup."]


def test_le_mock_n_est_plus_efface_par_la_deduplication():
    s = _session(SourceFactice())
    for i in range(3):
        s._merge_result(MockProvider().transcribe(BLOC * 50, RATE, i * 4.25, "fr"))
    assert len(s.segments()) == 3

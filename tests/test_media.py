import wave

import numpy as np
import pytest
from medias import ecrire, video_sans_son

from snappy import media
from snappy.media import DecodeError, decode_to_wav, iter_windows

# (extension, codec) : les formats courants, audio et vidéo
FORMATS = [
    ("mp3", "libmp3lame"), ("m4a", "aac"), ("aac", "aac"), ("ogg", "libopus"), ("opus", "libopus"), ("flac", "flac"),
    ("wav", "pcm_s16le"), ("wma", "wmav2"), ("mka", "flac"), ("aiff", "pcm_s16be"),
]
VIDEOS = [("mp4", "aac"), ("mov", "aac"), ("mkv", "libopus"), ("webm", "libopus"), ("avi", "libmp3lame")]


def _lire(chemin):
    with wave.open(str(chemin)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


@pytest.mark.parametrize("ext,codec", FORMATS + VIDEOS, ids=[f[0] for f in FORMATS + VIDEOS])
def test_les_formats_courants_sont_lus_sans_conversion(tmp_path, ext, codec):
    source = ecrire(tmp_path / f"essai.{ext}", codec, secondes=3, video=(ext, codec) in VIDEOS)
    avancement = []
    secondes, annoncee = decode_to_wav(source, tmp_path / "sortie.wav", lambda f, s: avancement.append(f))
    rate, canaux, largeur, trames = _lire(tmp_path / "sortie.wav")
    assert (rate, canaux, largeur) == (16000, 1, 2)
    assert secondes == pytest.approx(3, abs=0.15) and trames == round(secondes * 16000)
    assert annoncee is None or annoncee == pytest.approx(3, abs=0.2)
    assert avancement and max(f for f in avancement if f is not None) > 0.8


def test_le_son_est_conserve(tmp_path):
    decode_to_wav(ecrire(tmp_path / "a.mp3", "libmp3lame", 2), tmp_path / "s.wav")
    with wave.open(str(tmp_path / "s.wav")) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    assert 0.15 < np.sqrt(np.mean(pcm[4000:-4000] ** 2)) < 0.3  # sinus d'amplitude 0,3 → efficace ≈ 0,21


def test_video_sans_piste_audio(tmp_path):
    with pytest.raises(DecodeError, match="aucune piste audio"):
        decode_to_wav(video_sans_son(tmp_path / "muet.mp4"), tmp_path / "s.wav")


def test_fichier_qui_n_est_pas_un_media(tmp_path):
    faux = tmp_path / "notes.mp3"
    faux.write_text("ceci n'est pas du son " * 50)
    with pytest.raises(DecodeError, match="lisible|aucune piste"):
        decode_to_wav(faux, tmp_path / "s.wav")


def test_arret_pendant_la_lecture(tmp_path):
    source = ecrire(tmp_path / "long.flac", "flac", secondes=20)
    secondes, _ = decode_to_wav(source, tmp_path / "s.wav", checkpoint=lambda: True)
    assert secondes == 0


def test_fenetres_contigues_coupees_dans_le_silence(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "WINDOW_SECONDS", 6)
    monkeypatch.setattr(media, "SEARCH_SECONDS", 3)
    decode_to_wav(ecrire(tmp_path / "a.flac", "flac", secondes=14, silence_a=4.2), tmp_path / "s.wav")
    fenetres = list(iter_windows(tmp_path / "s.wav"))
    total = sum(f.size for _, f in fenetres)
    assert total == _lire(tmp_path / "s.wav")[3]
    debuts = [d for d, _ in fenetres]
    for (d1, f1), d2 in zip(fenetres, debuts[1:]):
        assert d1 + f1.size / 16000 == pytest.approx(d2)  # aucun trou, aucun recouvrement
    assert 4.2 <= debuts[1] <= 5.2  # première coupure dans la seconde de silence, pas à 6 s pile

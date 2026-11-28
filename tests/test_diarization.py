from snappy.diarization import _best, _merge, validate_diarization_model
from snappy.models import TranscriptSegment, TranscriptWord

TOURS = [(0.0, 2.0, "SPEAKER_00"), (2.0, 5.0, "SPEAKER_01")]


def test_locuteur_dominant_et_repli_sur_le_plus_proche():
    assert _best(TOURS, 0.5, 1.5) == "SPEAKER_00"
    assert _best(TOURS, 4.0, 4.5) == "SPEAKER_01"
    assert _best(TOURS, 9.0, 9.5) == "SPEAKER_01"
    assert _best([], 0, 1) is None


def test_segment_scinde_au_changement_de_locuteur():
    mots = (TranscriptWord(0.1, 0.6, "Bonjour"), TranscriptWord(1.0, 1.5, "Paul"),
            TranscriptWord(2.2, 2.7, "Merci"), TranscriptWord(3.0, 3.4, "Marie"))
    sortie = _merge([TranscriptSegment(0.1, 3.4, "Bonjour Paul Merci Marie", words=mots)], TOURS)
    assert [(s.speaker, s.text) for s in sortie] == [("SPEAKER_00", "Bonjour Paul"), ("SPEAKER_01", "Merci Marie")]


def test_segment_sans_mots_garde_son_texte():
    sortie = _merge([TranscriptSegment(2.5, 4.0, "Texte importé")], TOURS)
    assert [(s.speaker, s.text) for s in sortie] == [("SPEAKER_01", "Texte importé")]


def test_validation_du_pipeline(tmp_path):
    assert validate_diarization_model("")[0] is False
    assert "introuvable" in validate_diarization_model(str(tmp_path / "absent"))[1]
    ok, detail = validate_diarization_model(str(tmp_path))
    assert not ok and "config.yaml" in detail


def test_config_yaml_piege_refuse(tmp_path):
    """config.yaml désigne la classe que pyannote instancie : seule une classe pyannote est acceptée."""
    for f in ("embedding/pytorch_model.bin", "segmentation/pytorch_model.bin", "plda/plda.npz", "plda/xvec_transform.npz"):
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("x")
    (tmp_path / "config.yaml").write_text("pipeline:\n  name: subprocess.Popen\n  params:\n    args: calc.exe\n")
    ok, detail = validate_diarization_model(str(tmp_path))
    assert not ok and "subprocess.Popen" in detail
    (tmp_path / "config.yaml").write_text("version: 3.1.0\npipeline:\n  name: pyannote.audio.pipelines.SpeakerDiarization\n  params:\n    clustering: VBxClustering\n")
    assert validate_diarization_model(str(tmp_path))[0] is True

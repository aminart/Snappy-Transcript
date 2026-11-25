from __future__ import annotations

import importlib.metadata
from collections.abc import Iterator

import numpy as np
from dataclasses import dataclass
from pathlib import Path

from .base import TranscriptionProvider
from ..models import TranscriptSegment, TranscriptWord


@dataclass(frozen=True)
class ModelValidation:
    valid: bool
    path: Path | None
    message: str
    missing: tuple[str, ...] = ()


def validate_ctranslate2_model(model_path: str) -> ModelValidation:
    """Validate the minimal files expected from a local faster-whisper/CTranslate2 model."""
    raw = (model_path or "").strip().strip('"')
    if not raw:
        return ModelValidation(False, None, "Aucun dossier de modèle renseigné.")

    path = Path(raw).expanduser()
    if not path.is_dir():
        return ModelValidation(False, path, f"Dossier introuvable : {path}")

    required = ("config.json", "model.bin", "tokenizer.json")
    missing = tuple(name for name in required if not (path / name).is_file())
    if missing:
        return ModelValidation(
            False, path,
            "Ce dossier ne ressemble pas à un modèle CTranslate2 complet.",
            missing,
        )

    return ModelValidation(True, path, "Modèle CTranslate2 détecté.")


class LocalWhisperProvider(TranscriptionProvider):
    def configure(self, vad_filter: bool, glossary: str) -> None:
        """Réglages propres à chaque session : un modèle préchargé peut ainsi servir à la session suivante."""
        self.vad_filter = vad_filter
        self.glossary = " ".join((glossary or "").replace(",", " ").replace(";", " ").split())

    def __init__(self, model_path: str, cpu_threads: int = 4, vad_filter: bool = True, acceleration: str = "auto", glossary: str = ""):
        validation = validate_ctranslate2_model(model_path)
        if not validation.valid:
            suffix = f" Fichiers manquants : {', '.join(validation.missing)}." if validation.missing else ""
            raise ValueError(validation.message + suffix)

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper n'est pas installé dans ce venv. "
                "Exécute : python -m pip install -r requirements-stt.txt"
            ) from exc

        self.model_path = validation.path
        self.configure(vad_filter, glossary)
        self.faster_whisper_version = importlib.metadata.version("faster-whisper")
        try:
            self.ctranslate2_version = importlib.metadata.version("ctranslate2")
        except importlib.metadata.PackageNotFoundError:
            self.ctranslate2_version = "unknown"
        self.requested_acceleration = acceleration
        self.device = "cpu"
        self.compute_type = "int8"
        self.acceleration_fallback = None

        if acceleration != "cpu":
            from .cuda_runtime import prepare_cuda_runtime
            cuda = prepare_cuda_runtime()
            if cuda.ready:
                try:
                    self.model = WhisperModel(str(self.model_path), device="cuda", compute_type="float16", local_files_only=True)
                    self.device, self.compute_type = "cuda", "float16"
                except Exception as exc:
                    if acceleration == "gpu":
                        raise RuntimeError(f"GPU NVIDIA demandé mais initialisation CUDA impossible : {type(exc).__name__}: {exc}") from exc
                    self.acceleration_fallback = f"CUDA -> CPU : {type(exc).__name__}: {exc}"
            elif acceleration == "gpu":
                raise RuntimeError("GPU NVIDIA demandé mais CUDA n'est pas prêt : " + cuda.detail)
            else:
                self.acceleration_fallback = "CUDA -> CPU : " + cuda.detail

        if self.device == "cpu":
            self.model = WhisperModel(str(self.model_path), device="cpu", compute_type="int8", cpu_threads=cpu_threads, local_files_only=True)

    def transcribe(self, pcm: bytes, sample_rate: int, offset: float, language: str) -> list[TranscriptSegment]:
        if not pcm:
            return []
        # Les blocs du micro sont déjà en PCM16 mono : un tableau NumPy évite le décodeur de fichiers (PyAV/FFmpeg).
        return list(self.transcribe_stream(np.frombuffer(pcm, dtype=np.int16), offset, language))

    def transcribe_stream(self, samples: np.ndarray, offset: float, language: str) -> Iterator[TranscriptSegment]:
        """Segments au fur et à mesure du décodage (fichiers : progression et arrêt possibles entre deux segments).

        `samples` : PCM16 mono à 16 kHz ; faster-whisper attend du float32 normalisé entre -1 et 1.
        """
        if samples.size == 0:
            return
        audio = samples.astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(
            audio,
            language=None if language == "auto" else language,
            beam_size=1,
            vad_filter=self.vad_filter,
            condition_on_previous_text=False,
            word_timestamps=True,
            hotwords=self.glossary or None,
            initial_prompt=(f"Vocabulaire et noms propres possibles : {self.glossary}" if self.glossary else None),
        )
        for s in segments:
            text = s.text.strip()
            if not text:
                continue
            words = tuple(
                TranscriptWord(
                    offset + float(w.start if w.start is not None else s.start),
                    offset + float(w.end if w.end is not None else s.end),
                    (w.word or "").strip(),
                )
                for w in (s.words or [])
                if (w.word or "").strip()
            )
            yield TranscriptSegment(offset + float(s.start), offset + float(s.end), text, words=words)

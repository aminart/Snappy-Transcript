"""Lecture des fichiers audio et vidéo : n'importe quel format lu par FFmpeg (via PyAV) → WAV PCM16 mono 16 kHz.

PyAV embarque ses propres bibliothèques FFmpeg : aucune installation ni conversion préalable n'est nécessaire. Le WAV
produit sert ensuite à tout le reste (transcription, lecteur synchronisé, diarisation), quel que soit le format d'origine.
"""
from __future__ import annotations

import re
import wave
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000

# Proposés dans le sélecteur de fichiers. Tout autre format lu par FFmpeg fonctionne aussi (choix « Tous les fichiers »).
EXTENSIONS = (
    # audio
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".aif", ".aiff", ".alac", ".amr", ".ac3",
    ".mka", ".caf", ".weba",
    # vidéo
    ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".3gp", ".flv",
)

# Transcription par fenêtres d'environ 10 minutes : la mémoire reste bornée même pour une réunion de 4 heures.
# Chaque coupure est placée sur le passage le plus silencieux des 30 dernières secondes de la fenêtre.
WINDOW_SECONDS = 600
SEARCH_SECONDS = 30


class DecodeError(Exception):
    """Fichier illisible : message destiné à l'utilisateur."""


def decode_to_wav(
    source: Path,
    target: Path,
    progress: Callable[[float | None, float], None] = lambda fraction, seconds: None,
    checkpoint: Callable[[], bool] = lambda: False,
) -> tuple[float, float | None]:
    """Décode la première piste audio de `source` dans `target`.

    `progress` reçoit l'avancement (0 à 1, ou None si la durée du fichier est inconnue) et les secondes déjà lues ; `checkpoint` est appelé
    régulièrement et interrompt la lecture s'il renvoie True (arrêt demandé). Renvoie (secondes décodées, durée annoncée).
    """
    try:
        import av
    except ImportError as exc:
        raise DecodeError("La lecture des fichiers (PyAV) n'est pas incluse dans cette installation.") from exc

    try:
        container = av.open(str(source))
    except Exception as exc:  # av.error.* : format inconnu, fichier abîmé, protégé…
        raise DecodeError("Ce fichier n'est pas un fichier audio ou vidéo lisible : il est peut-être endommagé, protégé "
                          f"(DRM) ou d'un format inconnu. Détail : {_cause(exc)}.") from exc

    written = 0
    try:
        if not container.streams.audio:
            raise DecodeError("Ce fichier ne contient aucune piste audio.")
        stream = container.streams.audio[0]
        stream.thread_type = "AUTO"
        announced = _duration(container, stream)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        bad_packets = 0

        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)

            def write(frames) -> None:
                nonlocal written
                for out in frames:
                    pcm = out.to_ndarray().astype(np.int16, copy=False).reshape(-1)
                    wav.writeframes(pcm.tobytes())
                    written += pcm.size

            for packet in container.demux(stream):
                if checkpoint():
                    break
                try:
                    frames = packet.decode()
                except av.error.InvalidDataError:
                    bad_packets += 1  # paquet abîmé : on saute ce fragment plutôt que d'abandonner tout le fichier
                    if bad_packets > 200:
                        raise DecodeError("Trop de données illisibles : le fichier semble endommagé.")
                    continue
                for frame in frames:
                    write(resampler.resample(frame))
                    fraction = None
                    if announced and frame.time is not None:
                        fraction = min(1.0, max(0.0, float(frame.time) / announced))
                    progress(fraction, written / SAMPLE_RATE)
            write(resampler.resample(None))  # vide le tampon du rééchantillonneur
    except DecodeError:
        raise
    except Exception as exc:
        raise DecodeError(f"Lecture du fichier interrompue ({_cause(exc)}).") from exc
    finally:
        container.close()

    if written == 0 and not checkpoint():
        raise DecodeError("La piste audio de ce fichier est vide.")
    return written / SAMPLE_RATE, announced


def iter_windows(wav_path: Path, start_at: float = 0.0) -> Iterator[tuple[float, np.ndarray]]:
    """Découpe le WAV en fenêtres (début en secondes, échantillons int16), coupées dans un silence."""
    window, search = int(WINDOW_SECONDS * SAMPLE_RATE), int(SEARCH_SECONDS * SAMPLE_RATE)
    with wave.open(str(wav_path), "rb") as wav:
        total = wav.getnframes()
        pos = min(total, int(start_at * SAMPLE_RATE))
        while pos < total:
            end = min(total, pos + window)
            if end < total:
                end = _quietest_cut(wav, max(pos + 1, end - search), end)
            wav.setpos(pos)
            samples = np.frombuffer(wav.readframes(end - pos), dtype=np.int16)
            yield pos / SAMPLE_RATE, samples
            pos = end


def _quietest_cut(wav: wave.Wave_read, start: int, end: int) -> int:
    """Position (en échantillons) du bloc de 100 ms le plus silencieux entre start et end."""
    block = SAMPLE_RATE // 10
    wav.setpos(start)
    samples = np.frombuffer(wav.readframes(end - start), dtype=np.int16).astype(np.float32)
    n = samples.size // block
    if n < 2:
        return end
    energy = np.square(samples[: n * block].reshape(n, block)).mean(axis=1)
    return start + int(np.argmin(energy)) * block + block // 2


def _duration(container, stream) -> float | None:
    if container.duration:
        return container.duration / 1_000_000
    if stream.duration and stream.time_base:
        return float(stream.duration * stream.time_base)
    return None


def _cause(exc: Exception) -> str:
    """Message FFmpeg sans le code numérique ni le chemin du fichier : « Invalid data found when processing input »."""
    text = re.sub(r"^\[Errno -?\d+\]\s*", "", str(exc).strip())
    text = text.split(": '", 1)[0].strip()
    return text or type(exc).__name__

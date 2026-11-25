"""Fabrique de vrais fichiers audio et vidéo de test avec PyAV (tous les encodeurs sont dans ses bibliothèques FFmpeg)."""
from pathlib import Path

import av
import numpy as np


def ton(secondes: float, rate: int = 44100, canaux: int = 2, silence_a: float | None = None) -> np.ndarray:
    """Signal float32 (canaux, échantillons) : un ton de 440 Hz, avec éventuellement 1 s de silence à `silence_a`."""
    t = np.arange(int(secondes * rate)) / rate
    signal = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    if silence_a is not None:
        signal[int(silence_a * rate):int((silence_a + 1) * rate)] = 0
    return np.tile(signal, (canaux, 1))


def ecrire(chemin: Path, codec: str, secondes: float = 3.0, rate: int = 44100, video: bool = False,
           silence_a: float | None = None) -> Path:
    if codec == "libopus":
        rate = 48000  # Opus n'encode qu'à 48 kHz (et quelques sous-multiples)
    sortie = av.open(str(chemin), "w")
    if video:
        v = sortie.add_stream("libvpx" if chemin.suffix == ".webm" else "mpeg4", rate=25)
        v.width, v.height, v.pix_fmt = 64, 48, "yuv420p"
    a = sortie.add_stream(codec, rate=rate)
    a.layout = "stereo"
    a.bit_rate = 128_000
    cible = av.AudioResampler(format=a.format.name, layout="stereo", rate=rate)
    signal = ton(secondes, rate, silence_a=silence_a)
    pas = 1024
    image_suivante = 0  # horodatage de la prochaine image vidéo (25 i/s), jamais deux fois le même
    for i in range(0, signal.shape[1], pas):
        bloc = np.ascontiguousarray(signal[:, i:i + pas])
        trame = av.AudioFrame.from_ndarray(bloc, format="fltp", layout="stereo")
        trame.sample_rate, trame.pts = rate, i
        for t in cible.resample(trame):
            for paquet in a.encode(t):
                sortie.mux(paquet)
        while video and image_suivante <= i / rate * 25:
            image = av.VideoFrame.from_ndarray(np.zeros((48, 64, 3), np.uint8), format="rgb24")
            image.pts = image_suivante
            image_suivante += 1
            for paquet in v.encode(image):
                sortie.mux(paquet)
    for t in cible.resample(None):
        for paquet in a.encode(t):
            sortie.mux(paquet)
    for paquet in a.encode(None):
        sortie.mux(paquet)
    if video:
        for paquet in v.encode(None):
            sortie.mux(paquet)
    sortie.close()
    return chemin


def video_sans_son(chemin: Path) -> Path:
    sortie = av.open(str(chemin), "w")
    v = sortie.add_stream("mpeg4", rate=25)
    v.width, v.height, v.pix_fmt = 64, 48, "yuv420p"
    for i in range(25):
        image = av.VideoFrame.from_ndarray(np.zeros((48, 64, 3), np.uint8), format="rgb24")
        image.pts = i
        for paquet in v.encode(image):
            sortie.mux(paquet)
    for paquet in v.encode(None):
        sortie.mux(paquet)
    sortie.close()
    return chemin

from __future__ import annotations

import queue

from .base import AudioSource


class MicrophoneSource(AudioSource):
    def __init__(self, device: int | None, sample_rate: int = 16000, channels: int = 1, block_ms: int = 100):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = int(sample_rate * block_ms / 1000)
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            # PortAudio status is intentionally not fatal; the recorder can continue.
            pass
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            # Drop oldest-ish live data rather than blocking the PortAudio callback.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(bytes(indata))
            except queue.Empty:
                pass

    def start(self) -> None:
        import sounddevice as sd  # chargé ici : PortAudio peut manquer sur le poste
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=self.device,
            channels=self.channels,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def read_chunk(self, timeout: float = 0.2) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


def list_input_devices(sd=None) -> list[dict]:
    """Microphones, une ligne par appareil, le micro par défaut en premier.

    Sous Windows, PortAudio présente chaque micro plusieurs fois (MME, DirectSound, WASAPI, WDM-KS) et MME coupe les
    noms à 31 caractères : on ne garde que l'API par défaut (celle qu'ouvre l'enregistrement), avec le nom complet
    donné par WASAPI, et sans les entrées « mappeur » qui ne désignent pas un appareil précis."""
    if sd is None:
        import sounddevice as sd
    appareils = list(sd.query_devices())
    apis = list(sd.query_hostapis())
    try:
        api_defaut = int(sd.default.hostapi)
    except Exception:
        api_defaut = -1
    try:
        entree_defaut = int(sd.default.device[0])
    except Exception:
        entree_defaut = -1
    nom_api = lambda d: str(apis[int(d.get("hostapi", 0))]["name"]) if apis and 0 <= int(d.get("hostapi", 0)) < len(apis) else ""  # noqa: E731
    entrees = [(i, d) for i, d in enumerate(appareils) if int(d.get("max_input_channels", 0)) > 0]
    windows = any("WASAPI" in nom_api(d) or "MME" in nom_api(d) for _, d in entrees)
    if windows and api_defaut >= 0:
        complets = [str(d.get("name", "")) for _, d in entrees if "WASAPI" in nom_api(d)]
        gardes = [(i, d) for i, d in entrees if int(d.get("hostapi", -1)) == api_defaut]
    else:
        complets, gardes = [], entrees
    devices, vus = [], set()
    for index, info in gardes:
        nom = str(info.get("name", f"Device {index}")).strip()
        bas = nom.lower()
        if any(m in bas for m in ("mixage stéréo", "stereo mix", "what u hear", "wave out mix", "mixage stereo")):
            continue  # le son de l'ordinateur, pas un micro : il se choisit avec « Tout le son du PC »
        if windows and ("mappeur" in nom.lower() or "mapper" in nom.lower() or "pilote de capture" in nom.lower()
                        or "primary sound capture" in nom.lower()):
            continue
        complet = next((c for c in complets if c.startswith(nom) and len(c) > len(nom)), nom)
        if complet in vus:
            continue
        vus.add(complet)
        devices.append({
            "index": index,
            "name": complet,
            "channels": int(info.get("max_input_channels", 0)),
            "default_samplerate": int(info.get("default_samplerate", 0)),
            "default": index == entree_defaut,
        })
    devices.sort(key=lambda d: not d["default"])
    return devices

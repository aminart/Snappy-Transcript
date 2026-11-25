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


def list_input_devices() -> list[dict]:
    import sounddevice as sd
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) > 0:
            devices.append({
                "index": index,
                "name": str(info.get("name", f"Device {index}")),
                "channels": int(info.get("max_input_channels", 0)),
                "default_samplerate": int(info.get("default_samplerate", 0)),
            })
    return devices

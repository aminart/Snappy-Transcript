from abc import ABC, abstractmethod


class AudioSource(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def read_chunk(self, timeout: float = 0.2) -> bytes | None: ...

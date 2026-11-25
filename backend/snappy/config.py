from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    sample_rate: int = 16000
    channels: int = 1
    block_ms: int = 100


CONFIG = AppConfig()

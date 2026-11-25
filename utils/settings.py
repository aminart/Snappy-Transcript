from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

# Paramètres propres à la distribution portable.
RELEASE_DIR = Path(__file__).resolve().parents[2]
SETTINGS_DIR = RELEASE_DIR / "settings"
SETTINGS_FILE = SETTINGS_DIR / "user_settings.json"

_WRITE_LOCK = threading.RLock()


def load_settings() -> dict:
    try:
        if SETTINGS_FILE.is_file():
            data = json.loads(
                SETTINGS_FILE.read_text(encoding="utf-8")
            )
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass

    return {}


def save_setting(key: str, value) -> Path:
    with _WRITE_LOCK:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

        data = load_settings()
        data[key] = value

        tmp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".tmp",
                prefix="settings_",
                dir=SETTINGS_DIR,
                delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)
                json.dump(data, tmp, ensure_ascii=False, indent=2)

            os.replace(tmp_path, SETTINGS_FILE)

        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        return SETTINGS_FILE
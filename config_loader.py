"""Resolve the correct config.py path and load settings from disk.

When running as a PyInstaller exe, __file__ points to a temporary
extraction directory (_MEIxxxxx).  This module uses sys.executable
to locate config.py next to the .exe instead.
"""

import os
import sys
import types


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.py")

_DEFAULTS = {
    "AZURE_SPEECH_KEY": "",
    "AZURE_SPEECH_REGION": "swedencentral",
    "AZURE_VOICE_NAME": "sv-SE-MattiasNeural",
    "HOTKEY_READ_SELECTED": "ctrl+alt+s",
    "HOTKEY_SCREENSHOT_OCR": "ctrl+alt+o",
    "LANGUAGE": "sv",
    "CLIPBOARD_DELAY_MS": 150,
}


def load() -> types.SimpleNamespace:
    """Read config.py from disk and return a namespace with all settings."""
    cfg = types.SimpleNamespace(**_DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            code = f.read()
        d: dict = {}
        exec(compile(code, CONFIG_PATH, "exec"), d)
        for key in _DEFAULTS:
            if key in d:
                setattr(cfg, key, d[key])
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[config_loader] Error loading {CONFIG_PATH}: {exc}")
    return cfg

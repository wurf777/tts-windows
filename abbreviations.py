"""Abbreviation expansion — load/save/expand abbreviation lists.

abbreviations.json is stored next to config.py (handled by config_loader.APP_DIR).
Format: {"sv": {"obs": "observera", ...}, "en": {...}}
"""

import json
import os
import re
from typing import Dict, Optional

import config_loader

ABBREVS_PATH = os.path.join(config_loader.APP_DIR, "abbreviations.json")


def _load_all() -> dict:
    try:
        with open(ABBREVS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[abbreviations] Error loading {ABBREVS_PATH}: {exc}")
    return {}


def _save_all(all_abbrevs: dict) -> None:
    with open(ABBREVS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_abbrevs, f, ensure_ascii=False, indent=2)


def _is_legacy(data: dict) -> bool:
    """True if data is old flat-dict format (all values are strings)."""
    if not data:
        return False
    return all(isinstance(v, str) for v in data.values())


def _migrate(legacy: dict, lang: str) -> None:
    _save_all({lang: legacy})


def load(lang: Optional[str] = None) -> Dict[str, str]:
    """Load abbreviations for the given language (default: active config language)."""
    if lang is None:
        lang = config_loader.load().LANGUAGE
    data = _load_all()
    if not data:
        return {}
    if _is_legacy(data):
        _migrate(data, lang)
        return {str(k): str(v) for k, v in data.items()}
    lang_data = data.get(lang, {})
    if not isinstance(lang_data, dict):
        return {}
    return {str(k): str(v) for k, v in lang_data.items()}


def save(abbrevs: Dict[str, str], lang: Optional[str] = None) -> None:
    """Write abbreviations for the given language, preserving other languages."""
    if lang is None:
        lang = config_loader.load().LANGUAGE
    raw = _load_all()
    if _is_legacy(raw):
        raw = {lang: raw}
    raw[lang] = abbrevs
    _save_all(raw)


def _build_pattern(abbrevs: Dict[str, str]) -> Optional[re.Pattern]:
    if not abbrevs:
        return None
    # Longest-first so "t.ex." doesn't get shadowed by "t"
    keys_sorted = sorted(abbrevs.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in keys_sorted)
    # (?<!\w)/(?!\w) instead of \b — handles dots and Swedish chars correctly
    return re.compile(r"(?<!\w)(?:" + alternation + r")(?!\w)", re.IGNORECASE)


def _make_replacer(abbrevs: Dict[str, str]):
    lower_map = {k.lower(): v for k, v in abbrevs.items()}

    def replacer(match: re.Match) -> str:
        return lower_map.get(match.group(0).lower(), match.group(0))

    return replacer


def expand(text: str, abbrevs: Optional[Dict[str, str]] = None) -> str:
    """Return text with all abbreviations expanded. Loads from disk if abbrevs is None."""
    if abbrevs is None:
        abbrevs = load()
    if not abbrevs:
        return text
    pattern = _build_pattern(abbrevs)
    if pattern is None:
        return text
    return pattern.sub(_make_replacer(abbrevs), text)

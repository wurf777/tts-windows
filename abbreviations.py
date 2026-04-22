"""Abbreviation expansion — load/save/expand abbreviation lists.

abbreviations.json is stored next to config.py (handled by config_loader.APP_DIR).
"""

import json
import os
import re

import config_loader

ABBREVS_PATH = os.path.join(config_loader.APP_DIR, "abbreviations.json")


def load() -> dict[str, str]:
    """Load abbreviations from disk. Returns {} if file is missing or invalid."""
    try:
        with open(ABBREVS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[abbreviations] Error loading {ABBREVS_PATH}: {exc}")
    return {}


def save(abbrevs: dict[str, str]) -> None:
    """Write abbreviations to disk."""
    with open(ABBREVS_PATH, "w", encoding="utf-8") as f:
        json.dump(abbrevs, f, ensure_ascii=False, indent=2)


def _build_pattern(abbrevs: dict[str, str]) -> re.Pattern | None:
    if not abbrevs:
        return None
    # Longest-first so "t.ex." doesn't get shadowed by "t"
    keys_sorted = sorted(abbrevs.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in keys_sorted)
    # (?<!\w)/(?!\w) instead of \b — handles dots and Swedish chars correctly
    return re.compile(r"(?<!\w)(?:" + alternation + r")(?!\w)", re.IGNORECASE)


def _make_replacer(abbrevs: dict[str, str]):
    lower_map = {k.lower(): v for k, v in abbrevs.items()}

    def replacer(match: re.Match) -> str:
        return lower_map.get(match.group(0).lower(), match.group(0))

    return replacer


def expand(text: str, abbrevs: dict[str, str] | None = None) -> str:
    """Return text with all abbreviations expanded. Loads from disk if abbrevs is None."""
    if abbrevs is None:
        abbrevs = load()
    if not abbrevs:
        return text
    pattern = _build_pattern(abbrevs)
    if pattern is None:
        return text
    return pattern.sub(_make_replacer(abbrevs), text)

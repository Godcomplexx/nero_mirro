"""Shared text validation and sanitisation helpers.

Every function that was previously duplicated between ``web/app.py``,
``video_analysis/plugin.py`` and ``appearance_response.py`` now lives here
as a single source of truth.
"""
from __future__ import annotations

import re


def is_mostly_cyrillic(text: str, *, threshold: float = 0.6) -> bool:
    """Return *True* if at least *threshold* of letter characters are Cyrillic."""
    letters = [ch for ch in str(text or "") if ch.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    return cyrillic / len(letters) >= threshold


def is_safe_russian_text(
    text: str,
    *,
    min_cyrillic_ratio: float = 0.82,
    max_foreign_tokens: int = 2,
) -> bool:
    """Validate that *text* is predominantly Russian with minimal foreign words."""
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return False

    letters = [ch for ch in cleaned if ch.isalpha()]
    if not letters:
        return False

    cyrillic_letters = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    if cyrillic_letters / len(letters) < min_cyrillic_ratio:
        return False

    foreign_tokens = 0
    for token in re.findall(r"[\w'-]+", cleaned, flags=re.UNICODE):
        token_letters = [ch for ch in token if ch.isalpha()]
        if len(token_letters) < 2:
            continue

        has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in token_letters)
        has_foreign = any(not ("\u0400" <= ch <= "\u04ff") for ch in token_letters)
        if has_cyrillic and has_foreign:
            return False
        if has_foreign:
            foreign_tokens += 1
            if foreign_tokens > max_foreign_tokens:
                return False

    return True


def sanitize_vision_description(text: str) -> str:
    """Clean and validate a vision-model generated description."""
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    blocked_markers = (
        "i am a large language model",
        "cannot generate images",
        "не могу генерировать изображения",
        "disclaimer:",
        "эмоция:",
    )
    if any(marker in lowered for marker in blocked_markers):
        return ""
    if len(cleaned) < 18:
        return ""
    if not is_safe_russian_text(cleaned):
        return ""
    return cleaned

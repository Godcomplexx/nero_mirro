"""Pure response analysis and scoring for GM-13."""
from __future__ import annotations

import re
import statistics
from typing import Any


IGNORED_WORDS = {
    "а", "в", "вот", "да", "еще", "ещё", "и", "или", "как", "может",
    "на", "ну", "это", "этот", "эта", "так", "там", "тоже",
}

IRREGULAR_FORMS = {
    "картошка": "картофель",
    "картошки": "картофель",
    "морковка": "морковь",
    "морковки": "морковь",
    "огурцы": "огурец",
    "перцы": "перец",
    "помидоры": "помидор",
    "редиски": "редис",
    "свёкла": "свекла",
    "свёклы": "свекла",
    "медведи": "медведь",
    "мыши": "мышь",
    "лошади": "лошадь",
    "стулья": "стул",
    "кресла": "кресло",
    "скамейки": "скамейка",
    "полки": "полка",
}


def _normalise_token(token: str, vocabulary: set[str]) -> str:
    direct = IRREGULAR_FORMS.get(token, token)
    if direct in vocabulary:
        return direct
    stem = token[:-1]
    candidates = (stem, f"{stem}а", f"{stem}я", f"{stem}ь", f"{stem}о")
    return next((candidate for candidate in candidates if candidate in vocabulary), token)


def analyse_category_response(transcript: str, vocabulary: set[str]) -> dict[str, Any]:
    raw_tokens = [
        token
        for token in re.findall(r"[а-яё-]+", transcript.lower())
        if token not in IGNORED_WORDS
    ]
    tokens = [_normalise_token(token, vocabulary) for token in raw_tokens]
    valid_words: list[str] = []
    invalid_words: list[str] = []
    repetitions: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            repetitions.append(token)
            continue
        seen.add(token)
        if token in vocabulary:
            valid_words.append(token)
        else:
            invalid_words.append(token)
    return {
        "tokens": tokens,
        "valid_words": valid_words,
        "invalid_words": invalid_words,
        "repetitions": repetitions,
    }


def score_gm13(events: list[dict[str, Any]]) -> dict[str, float | int]:
    valid_count = sum(len(event.get("valid_words") or ()) for event in events)
    repetition_count = sum(len(event.get("repetitions") or ()) for event in events)
    category_error_count = sum(len(event.get("invalid_words") or ()) for event in events)
    total_duration_ms = sum(float(event.get("duration_ms") or 0) for event in events)
    intervals = [
        float(event.get("duration_ms") or 0) / len(event.get("tokens") or ())
        for event in events
        if event.get("tokens")
    ]
    return {
        "l04_valid_word_count": valid_count,
        "l05_repetition_count": repetition_count,
        "l06_category_error_count": category_error_count,
        "l08_estimated_median_word_interval_ms": statistics.median(intervals) if intervals else 0.0,
        "l09_valid_words_per_minute": (
            valid_count * 60_000 / total_duration_ms if total_duration_ms else 0.0
        ),
    }

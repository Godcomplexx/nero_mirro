"""Pure response analysis and scoring for GM-16."""
from __future__ import annotations

import re
from typing import Any


IGNORED_WORDS = {
    "а", "в", "вот", "да", "еще", "ещё", "и", "или", "на", "ну", "это",
    "слово", "слова", "так",
}


def analyse_phonemic_response(transcript: str, letter: str) -> dict[str, Any]:
    tokens = [
        token
        for token in re.findall(r"[а-яё-]+", transcript.lower())
        if token not in IGNORED_WORDS
    ]
    required = letter.lower()
    valid_words: list[str] = []
    invalid_words: list[str] = []
    repetitions: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            repetitions.append(token)
            continue
        seen.add(token)
        if token.startswith(required):
            valid_words.append(token)
        else:
            invalid_words.append(token)
    return {
        "tokens": tokens,
        "valid_words": valid_words,
        "invalid_words": invalid_words,
        "repetitions": repetitions,
    }


def score_gm16(events: list[dict[str, Any]]) -> dict[str, float | int]:
    valid_count = sum(len(event.get("valid_words") or ()) for event in events)
    repetition_count = sum(len(event.get("repetitions") or ()) for event in events)
    invalid_count = sum(len(event.get("invalid_words") or ()) for event in events)
    duration_ms = sum(float(event.get("duration_ms") or 0) for event in events)
    token_count = sum(len(event.get("tokens") or ()) for event in events)
    return {
        "l04_valid_word_count": valid_count,
        "l05_repetition_count": repetition_count,
        "l06_rule_error_count": invalid_count,
        "l08_estimated_word_interval_ms": duration_ms / token_count if token_count else 0.0,
        "l09_valid_words_per_minute": (
            valid_count * 60_000 / duration_ms if duration_ms else 0.0
        ),
    }

from __future__ import annotations

from typing import Any


def score_gm14_words(
    words: list[dict[str, Any]], *, expected_word_count: int = 10
) -> dict[str, Any]:
    """Calculate GM-14 metrics from completed word records."""
    total_letters = sum(len(str(word.get("target") or "")) for word in words)
    correct_first_positions = sum(
        int(word.get("first_attempt_correct_positions") or 0) for word in words
    )
    first_try_words = sum(1 for word in words if int(word.get("attempt_count") or 0) == 1)
    repeated_attempts = sum(
        max(0, int(word.get("attempt_count") or 0) - 1) for word in words
    )
    return {
        "u01_first_attempt_word_accuracy": (
            first_try_words / len(words) if words else None
        ),
        "l03_letter_position_accuracy": (
            correct_first_positions / total_letters if total_letters else None
        ),
        "u04_duration_ms": sum(float(word.get("duration_ms") or 0.0) for word in words),
        "g10_repeated_attempts": repeated_attempts,
        "u06_complete": len(words) == expected_word_count,
        "u06_technically_valid": all(
            bool(word.get("attempts")) and bool(word.get("target")) for word in words
        ),
    }

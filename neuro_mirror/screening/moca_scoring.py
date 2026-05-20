from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


VOICE_MOCA_MAX_SCORE = 15

MEMORY_WORDS = ("лицо", "бархат", "церковь", "фиалка", "красный")
SERIAL_EXPECTED = (93, 86, 79, 72, 65)
DIGITS_FORWARD_EXPECTED = (2, 1, 8, 5, 4)
DIGITS_BACKWARD_EXPECTED = (2, 4, 7)

UNITS = {
    "ноль": 0,
    "один": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
}

TEENS = {
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
}

TENS = {
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
}


def score_moca_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    scored_tasks = [_score_task(task) for task in tasks]
    total = sum(int(task.get("score") or 0) for task in scored_tasks)
    percent = round(total / VOICE_MOCA_MAX_SCORE, 3) if VOICE_MOCA_MAX_SCORE else 0.0
    return {
        "score": total,
        "max_score": VOICE_MOCA_MAX_SCORE,
        "percent": percent,
        "interpretation": _interpret(total),
        "tasks": scored_tasks,
        "notes": (
            "Автоматический подсчет основан на распознанной речи и требует проверки специалистом. "
            "Это voice-only профиль MoCA без зрительно-пространственных заданий и ориентации."
        ),
    }


def _score_task(task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    transcript = str(task.get("transcript") or "")
    base = {
        **task,
        "score": 0,
        "max_score": 0,
        "status": "not_scored",
        "expected": "",
        "details": "",
    }

    if task_id in {"memory_1", "memory_2"}:
        return {
            **base,
            "details": "Проба заучивания: фиксируется, но не входит в итоговый балл.",
        }

    if task_id == "attention_digits_forward":
        return _score_digit_span(base, transcript, DIGITS_FORWARD_EXPECTED)

    if task_id == "attention_digits_backward":
        return _score_digit_span(base, transcript, DIGITS_BACKWARD_EXPECTED)

    if task_id == "attention_serial":
        return _score_serial_subtraction(base, transcript)

    if task_id == "language_sentence_1":
        expected = "я знаю только одно что иван это тот кто может сегодня помочь"
        return _score_similarity(base, transcript, expected)

    if task_id == "language_sentence_2":
        expected = "кошка всегда пряталась под диваном когда собаки были в комнате"
        return _score_similarity(base, transcript, expected)

    if task_id == "language_fluency":
        return _score_fluency(base, transcript)

    if task_id == "abstraction_1":
        return _score_abstraction(
            base,
            transcript,
            expected="транспорт / средство передвижения",
            markers=("транспорт", "передвиж", "езд", "ехать", "перемещ"),
        )

    if task_id == "abstraction_2":
        return _score_abstraction(
            base,
            transcript,
            expected="измерительные предметы",
            markers=("измер", "мер", "длин", "врем", "прибор", "инструмент"),
        )

    if task_id == "delayed_recall":
        return _score_delayed_recall(base, transcript)

    return base


def _score_digit_span(base: dict[str, Any], transcript: str, expected: tuple[int, ...]) -> dict[str, Any]:
    numbers = _extract_numbers(transcript)
    correct = tuple(numbers[: len(expected)]) == expected
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": " ".join(map(str, expected)),
        "details": f"Распознано: {' '.join(map(str, numbers)) or '-'}",
    }


def _score_serial_subtraction(base: dict[str, Any], transcript: str) -> dict[str, Any]:
    parts = [part.strip() for part in transcript.split("|") if part.strip()]
    if parts:
        answers = [_extract_numbers(part)[-1] for part in parts if _extract_numbers(part)]
    else:
        answers = _extract_numbers(transcript)
    # Allow ±1 tolerance: STT sometimes mishears a digit
    correct_count = sum(1 for answer, expected in zip(answers, SERIAL_EXPECTED) if abs(answer - expected) <= 1)
    if correct_count >= 4:
        score = 3
    elif correct_count >= 2:
        score = 2
    elif correct_count == 1:
        score = 1
    else:
        score = 0
    return {
        **base,
        "score": score,
        "max_score": 3,
        "status": "correct" if score == 3 else "partial" if score else "incorrect",
        "expected": " ".join(map(str, SERIAL_EXPECTED)),
        "details": f"Верных вычитаний: {correct_count}/5. Распознано: {' '.join(map(str, answers)) or '-'}",
    }


def _score_similarity(base: dict[str, Any], transcript: str, expected: str) -> dict[str, Any]:
    ratio = SequenceMatcher(None, _normalize_text(transcript), _normalize_text(expected)).ratio()
    correct = ratio >= 0.68
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": expected,
        "details": f"Сходство: {ratio:.2f}",
    }


def _score_fluency(base: dict[str, Any], transcript: str) -> dict[str, Any]:
    words = {
        word
        for word in _normalize_text(transcript).split()
        if len(word) > 1 and word.startswith("л")
    }
    correct = len(words) >= 11
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": "11+ слов на букву Л за 1 минуту",
        "details": f"Уникальных слов на Л: {len(words)}",
    }


def _score_abstraction(
    base: dict[str, Any],
    transcript: str,
    *,
    expected: str,
    markers: tuple[str, ...],
) -> dict[str, Any]:
    normalized = _normalize_text(transcript)
    correct = any(marker in normalized for marker in markers)
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": expected,
        "details": "Найдена категория." if correct else "Категория не найдена автоматически.",
    }


def _score_delayed_recall(base: dict[str, Any], transcript: str) -> dict[str, Any]:
    recalled = [word for word in MEMORY_WORDS if _contains_word_like(transcript, word)]
    return {
        **base,
        "score": len(recalled),
        "max_score": 5,
        "status": "correct" if len(recalled) == 5 else "partial" if recalled else "incorrect",
        "expected": ", ".join(MEMORY_WORDS),
        "details": f"Вспомнено: {', '.join(recalled) or '-'}",
    }


def _extract_numbers(text: str) -> list[int]:
    # First pass: merge digit groups joined by hyphens (e.g. "6-7" → 67, "9-3" → 93)
    merged = re.sub(r"(\d+)-(\d+)", lambda m: str(m.group(1)) + m.group(2), text)
    normalized = _normalize_text(merged)

    # Extract all digit sequences
    numbers = [int(match.group(0)) for match in re.finditer(r"\d+", normalized)]

    # Second pass: parse written-out Russian numbers from remaining text
    without_digits = re.sub(r"\d+", " ", normalized)
    tokens = without_digits.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "сто":
            # Check if followed by tens/units (e.g. "сто девяносто три")
            value = 100
            while index + 1 < len(tokens):
                next_tok = tokens[index + 1]
                if next_tok in TENS:
                    value += TENS[next_tok]
                    index += 1
                    if index + 1 < len(tokens) and tokens[index + 1] in UNITS:
                        value += UNITS[tokens[index + 1]]
                        index += 1
                    break
                elif next_tok in UNITS:
                    value += UNITS[next_tok]
                    index += 1
                    break
                else:
                    break
            numbers.append(value)
        elif token in TEENS:
            numbers.append(TEENS[token])
        elif token in TENS:
            value = TENS[token]
            if index + 1 < len(tokens) and tokens[index + 1] in UNITS:
                value += UNITS[tokens[index + 1]]
                index += 1
            numbers.append(value)
        elif token in UNITS:
            numbers.append(UNITS[token])
        index += 1
    return numbers


def _contains_word_like(text: str, expected: str) -> bool:
    normalized_expected = _normalize_text(expected)
    for word in _normalize_text(text).split():
        if word == normalized_expected:
            return True
        if SequenceMatcher(None, word, normalized_expected).ratio() >= 0.78:
            return True
    return False


def _normalize_text(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", " ", lowered).strip()


def _interpret(score: int) -> str:
    if score >= 13:
        return "Высокий результат voice-MoCA; требуется обычная клиническая интерпретация."
    if score >= 10:
        return "Промежуточный результат voice-MoCA; рекомендуется проверка ответов специалистом."
    return "Низкий результат voice-MoCA или плохое качество распознавания; нужна ручная проверка."

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


VOICE_MOCA_MAX_SCORE = 15

MEMORY_WORDS = ("лицо", "бархат", "церковь", "фиалка", "красный")
MEMORY_WORD_FORMS = {
    "лицо": ("лицо", "лица", "лицом", "лицу"),
    "бархат": (
        "бархат",
        "бархата",
        "бархатом",
        "бархатный",
    ),
    "церковь": ("церковь", "церкви", "церковью"),
    "фиалка": ("фиалка", "фиалки", "фиалку", "фиалкой"),
    "красный": (
        "красный",
        "красная",
        "красное",
        "красные",
        "красного",
        "красному",
        "красным",
    ),
}
SERIAL_EXPECTED = (93, 86, 79, 72, 65)
SERIAL_NUMBER_FORMS = {
    "одного": "один",
    "двух": "два",
    "трех": "три",
    "четырех": "четыре",
    "пяти": "пять",
    "шести": "шесть",
    "семи": "семь",
    "восьми": "восемь",
    "девяти": "девять",
    "двадцати": "двадцать",
    "тридцати": "тридцать",
    "сорока": "сорок",
    "пятидесяти": "пятьдесят",
    "шестидесяти": "шестьдесят",
    "семидесяти": "семьдесят",
    "восьмидесяти": "восемьдесят",
    "девяноста": "девяносто",
}
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


def score_moca_task(task_id: str, transcript: str) -> dict[str, Any]:
    """Оценить одно задание MoCA по идентификатору и транскрипции."""
    return _score_task({"task_id": task_id, "transcript": transcript})


def summarize_moca_tasks(
    scored_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Сформировать общий результат из уже оценённых заданий."""
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


def score_moca_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Оценить список заданий и вернуть баллы по заданиям и общий итог."""
    scored_tasks = [_score_task(task) for task in tasks]
    return summarize_moca_tasks(scored_tasks)


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
        return _score_sentence_words(base, transcript, expected)

    if task_id == "language_sentence_2":
        expected = "кошка всегда пряталась под диваном когда собаки были в комнате"
        return _score_sentence_words(base, transcript, expected)

    if task_id == "language_fluency":
        return _score_fluency(base, transcript)

    if task_id == "abstraction_1":
        return _score_abstraction(
            base,
            transcript,
            expected="транспорт / средство передвижения",
            word_stems=("транспорт", "передвиж", "перемещ", "езд", "ехать"),
        )

    if task_id == "abstraction_2":
        return _score_abstraction(
            base,
            transcript,
            expected="измерительные предметы",
            word_stems=(
                "измер",
                "замер",
                "мерить",
                "меряют",
                "длин",
                "врем",
                "прибор",
                "инструмент",
                "шкал",
                "делени",
                "цифр",
                "числ",
                "циферблат",
            ),
            fuzzy_phrases=("измерительный прибор",),
        )

    if task_id == "delayed_recall":
        return _score_delayed_recall(base, transcript)

    return base


def _score_digit_span(
    base: dict[str, Any],
    transcript: str,
    expected: tuple[int, ...],
) -> dict[str, Any]:
    numbers = _extract_numbers(transcript)
    expected_length = len(expected)
    correct = any(
        tuple(numbers[start : start + expected_length]) == expected
        for start in range(len(numbers) - expected_length + 1)
    )
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": " ".join(map(str, expected)),
        "details": (
            f"Точная последовательность "
            f"{'найдена' if correct else 'не найдена'}. "
            f"Распознано: {' '.join(map(str, numbers)) or '-'}"
        ),
    }


def _score_serial_subtraction(base: dict[str, Any], transcript: str) -> dict[str, Any]:
    extracted_numbers = _split_serial_compound_hundreds(
        _extract_numbers(_normalize_serial_number_forms(transcript))
    )
    # 100 — исходное число, а однозначные числа обычно являются вслух
    # произнесённым оператором («минус семь»), а не результатом вычитания.
    raw_answers = [
        number for number in extracted_numbers if 10 <= number < 100
    ]
    answers, corrected_answers = _remove_immediate_serial_corrections(
        raw_answers
    )
    transitions = list(zip((100, *answers), answers))
    correct_transitions = [
        (previous, current)
        for previous, current in transitions
        if previous - current == 7
    ][:5]
    correct_count = len(correct_transitions)
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
        "details": (
            f"Верных вычитаний: {correct_count}/5. "
            f"Верные переходы: "
            f"{_format_serial_transitions(correct_transitions)}. "
            f"Результаты: {' '.join(map(str, answers)) or '-'}. "
            f"Исправления: "
            f"{' '.join(map(str, corrected_answers)) or '-'}"
        ),
    }


def _normalize_serial_number_forms(text: str) -> str:
    """Привести падежные формы числительных к именительному падежу."""
    normalized = text.lower().replace("ё", "е")
    # В спонтанной речи глагол иногда проглатывается: «восьмидесяти семь,
    # это будет семьдесят три» означает 80 − 7, а не число 87. Служебное
    # слово не даёт общему парсеру склеить десяток и оператор вычитания.
    for source, target in SERIAL_NUMBER_FORMS.items():
        if target not in TENS:
            continue
        normalized = re.sub(
            rf"(?<![а-я]){source}\s+семь(?=\s+(?:это|будет))",
            f"{target} операция семь",
            normalized,
        )
    for source, target in SERIAL_NUMBER_FORMS.items():
        normalized = re.sub(
            rf"(?<![а-я]){source}(?![а-я])",
            target,
            normalized,
        )
    return normalized


def _split_serial_compound_hundreds(numbers: list[int]) -> list[int]:
    """Разделить склеенные ASR числа вида «сто девяносто три».

    В задании отсчёт всегда начинается со 100, поэтому распознанное число
    101–199 означает, что ASR объединила повтор исходного числа и следующий
    ответ: 193 преобразуется в 100, 93.
    """
    separated = []
    for number in numbers:
        if 100 < number < 200:
            separated.extend((100, number - 100))
        else:
            separated.append(number)
    return separated


def _remove_immediate_serial_corrections(
    answers: list[int],
) -> tuple[list[int], list[int]]:
    """Убрать один черновой ответ перед немедленным исправлением.

    Число пропускается только тогда, когда оно ошибочно относительно
    предыдущего принятого результата, а следующее число ровно на 7 меньше
    этого результата. Произвольные числа и длинные разрывы не пропускаются.
    """
    cleaned = []
    corrected = []
    previous = 100
    index = 0
    while index < len(answers):
        current = answers[index]
        has_replacement = index + 1 < len(answers)
        replacement = answers[index + 1] if has_replacement else 0
        looks_like_correction = has_replacement and (
            current == previous
            or abs(current - replacement) <= 2
            or (
                current % 10 == 0
                and current // 10 == replacement // 10
            )
        )
        if (
            previous - current != 7
            and looks_like_correction
            and previous - replacement == 7
        ):
            corrected.append(current)
            current = replacement
            index += 1
        cleaned.append(current)
        previous = current
        index += 1
    return cleaned, corrected


def _format_serial_transitions(transitions: list[tuple[int, int]]) -> str:
    """Подготовить найденные правильные вычитания для отчёта."""
    if not transitions:
        return "-"
    return ", ".join(
        f"{previous}→{current}"
        for previous, current in transitions
    )


def _score_sentence_words(
    base: dict[str, Any],
    transcript: str,
    expected: str,
) -> dict[str, Any]:
    """Проверить строгий порядок слов, разрешив изменение окончаний."""
    expected_words = _normalize_text(expected).split()
    actual_words = _normalize_text(transcript).split()
    same_length = len(actual_words) == len(expected_words)
    mismatches = [
        (index, expected_word, actual_word)
        for index, (expected_word, actual_word) in enumerate(
            zip(expected_words, actual_words),
            start=1,
        )
        if not _same_word_with_different_ending(expected_word, actual_word)
    ]
    correct = same_length and not mismatches

    if not same_length:
        details = (
            "Количество слов не совпало: "
            f"ожидалось {len(expected_words)}, распознано {len(actual_words)}."
        )
    elif mismatches:
        details = "Не совпали слова: " + "; ".join(
            f"{index}: {expected_word} ≠ {actual_word}"
            for index, expected_word, actual_word in mismatches
        )
    else:
        details = (
            "Строгая последовательность слов совпала; "
            "различия окончаний разрешены."
        )
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": expected,
        "details": details,
    }


def _same_word_with_different_ending(expected: str, actual: str) -> bool:
    """Сравнить слова, допуская замену не более трёх букв окончания."""
    if expected == actual:
        return True
    common_prefix_length = 0
    for expected_char, actual_char in zip(expected, actual):
        if expected_char != actual_char:
            break
        common_prefix_length += 1
    return (
        common_prefix_length >= 4
        and len(expected) - common_prefix_length <= 3
        and len(actual) - common_prefix_length <= 3
    )


def _score_fluency(base: dict[str, Any], transcript: str) -> dict[str, Any]:
    # Длительность здесь намеренно не проверяется: оценщик обрабатывает весь
    # диапазон аудио, который был передан между маркерами начала и окончания.
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
        "expected": "11+ уникальных слов на букву Л во всем диапазоне",
        "details": f"Уникальных слов на Л: {len(words)}",
    }


def _score_abstraction(
    base: dict[str, Any],
    transcript: str,
    *,
    expected: str,
    word_stems: tuple[str, ...],
    fuzzy_phrases: tuple[str, ...] = (),
) -> dict[str, Any]:
    normalized = _normalize_text(transcript)
    words = normalized.split()
    matched_rule = next(
        (
            stem
            for word in words
            for stem in word_stems
            if word.startswith(stem)
        ),
        "",
    )
    if not matched_rule:
        matched_rule = _find_fuzzy_phrase(words, fuzzy_phrases)
    correct = bool(matched_rule)
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": expected,
        "details": (
            f"Найдена категория: {matched_rule}."
            if correct
            else "Категория не найдена автоматически."
        ),
    }


def _find_fuzzy_phrase(
    words: list[str],
    expected_phrases: tuple[str, ...],
) -> str:
    """Найти фразу с типичными небольшими ошибками ASR."""
    for expected in expected_phrases:
        normalized_expected = _normalize_text(expected)
        expected_length = len(normalized_expected.split())
        for window_length in range(
            max(1, expected_length - 1),
            expected_length + 2,
        ):
            for start in range(len(words) - window_length + 1):
                candidate = " ".join(words[start : start + window_length])
                similarity = SequenceMatcher(
                    None,
                    candidate,
                    normalized_expected,
                ).ratio()
                if similarity >= 0.75:
                    return candidate
    return ""


def _score_delayed_recall(base: dict[str, Any], transcript: str) -> dict[str, Any]:
    recalled = [
        word
        for word in MEMORY_WORDS
        if _contains_word_like(transcript, word)
    ]
    return {
        **base,
        "score": len(recalled),
        "max_score": 5,
        "status": (
            "correct"
            if len(recalled) == 5
            else "partial" if recalled else "incorrect"
        ),
        "expected": ", ".join(MEMORY_WORDS),
        "details": f"Вспомнено: {', '.join(recalled) or '-'}",
    }


def _extract_numbers(text: str) -> list[int]:
    # First pass: merge digit groups joined by hyphens (e.g. "6-7" → 67, "9-3" → 93)
    merged = re.sub(r"(\d+)-(\d+)", lambda m: str(m.group(1)) + m.group(2), text)
    normalized = _normalize_text(merged)

    # Цифры и числа, записанные словами, извлекаются за один
    # проход, чтобы сохранить исходный порядок в смешанной записи.
    numbers = []
    tokens = normalized.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isdigit():
            numbers.append(int(token))
        elif token == "сто":
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
    expected_forms = MEMORY_WORD_FORMS.get(expected, (expected,))
    normalized_forms = tuple(_normalize_text(form) for form in expected_forms)
    for word in _normalize_text(text).split():
        if word in normalized_forms:
            return True
        if any(
            SequenceMatcher(None, word, form).ratio() >= 0.78
            for form in normalized_forms
        ):
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

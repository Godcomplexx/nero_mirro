from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


VOICE_MOCA_MAX_SCORE = 15

# ── Когнитивные домены ─────────────────────────────────────────────────────────
# Профиль строится по четырём доменам. Пробы заучивания (memory_1, memory_2)
# в балл не входят и потому ни к какому домену не отнесены: их результат
# фиксируется, но на профиль не влияет.
DOMAIN_MEMORY = "Память"
DOMAIN_ATTENTION = "Внимание"
DOMAIN_SPEECH = "Речь"
DOMAIN_ABSTRACTION = "Абстракция"

# Порядок задаёт порядок вывода профиля в отчёте.
COGNITIVE_DOMAINS: tuple[str, ...] = (
    DOMAIN_MEMORY,
    DOMAIN_ATTENTION,
    DOMAIN_SPEECH,
    DOMAIN_ABSTRACTION,
)

TASK_DOMAINS: dict[str, str] = {
    # Серийный счёт относится к вниманию, как в исходной методике.
    "attention_digits_forward": DOMAIN_ATTENTION,
    "attention_digits_backward": DOMAIN_ATTENTION,
    "attention_serial": DOMAIN_ATTENTION,
    "language_sentence_1": DOMAIN_SPEECH,
    "language_sentence_2": DOMAIN_SPEECH,
    "language_fluency": DOMAIN_SPEECH,
    "abstraction_1": DOMAIN_ABSTRACTION,
    "abstraction_2": DOMAIN_ABSTRACTION,
    "delayed_recall": DOMAIN_MEMORY,
}

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
SERIAL_CORRECTION_CUES = (
    "ой",
    "нет",
    "ошиб",
    "исправ",
    "запут",
    "пута",
    "господи",
    "проблем",
    "не помню",
    "не получается",
)
SENTENCE_ASR_WORD_REPLACEMENTS = {
    "диан": "диван",
    "зеваном": "диваном",
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


def domain_max_scores() -> dict[str, int]:
    """Максимум каждого домена, выведенный из правил оценки заданий.

    Значения не задаются вручную: иначе при изменении правила оценки любого
    задания максимум домена молча разошёлся бы с фактически достижимым.
    """
    totals = dict.fromkeys(COGNITIVE_DOMAINS, 0)
    for task_id, domain in TASK_DOMAINS.items():
        totals[domain] += int(score_moca_task(task_id, "")["max_score"])
    return totals


def summarize_domains(scored_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Когнитивный профиль: балл, максимум и нормированный дефицит по доменам.

    Нормированный дефицит D = (M − S) / M, где M — максимум домена,
    S — полученный балл. Значение лежит в диапазоне от 0 до 1: ноль
    соответствует полному выполнению, единица — отсутствию верных ответов.
    """
    maxima = domain_max_scores()
    earned = dict.fromkeys(COGNITIVE_DOMAINS, 0)
    for task in scored_tasks:
        domain = TASK_DOMAINS.get(str(task.get("task_id") or ""))
        if domain is not None:
            earned[domain] += int(task.get("score") or 0)

    profile: list[dict[str, Any]] = []
    for domain in COGNITIVE_DOMAINS:
        maximum = maxima[domain]
        score = max(0, min(earned[domain], maximum))
        profile.append({
            "domain": domain,
            "score": score,
            "max_score": maximum,
            "deficit": round((maximum - score) / maximum, 3) if maximum else None,
        })
    return profile


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
        "domains": summarize_domains(scored_tasks),
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
        return _score_sentence_words(
            base,
            transcript,
            expected,
            optional_asr_words=("это",),
        )

    if task_id == "language_sentence_2":
        expected = "кошка всегда пряталась под диваном когда собаки были в комнате"
        return _score_sentence_words(
            base,
            transcript,
            expected,
            optional_asr_words=("под", "в"),
        )

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
                "прибор",
                "инструмент",
                "шкал",
            ),
            exact_phrases=(
                "смирение",
                "извинени",
                "это время",
                "меры времени и длины",
                "меру времени и длины",
                "цифр блат",
                "тут циферблат а тут цифры",
                "циферблат общий",
                "сантиметр миллиметр",
                "сантиметрах миллиметр",
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
    normalized_transcript = _normalize_serial_number_forms(transcript)
    normalized_transcript = _normalize_fragmented_serial_numbers(
        normalized_transcript
    )
    extracted_numbers = _split_serial_compound_hundreds(
        _extract_numbers(normalized_transcript)
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
    transition_score = _serial_score_from_count(correct_count)

    # В естественной речи испытуемый часто повторяет операнд,
    # рассуждает вслух и исправляется. Это разрывает цепочку
    # соседних переходов. При явных признаках самокоррекции дополнительно
    # ищем эталонные ответы в правильном порядке, не удаляя ошибки.
    has_correction_cue = any(
        cue in normalized_transcript for cue in SERIAL_CORRECTION_CUES
    )
    ordered_expected_count = (
        _longest_serial_expected_subsequence(raw_answers)
        if has_correction_cue
        else 0
    )
    recovery_score = _serial_score_from_count(ordered_expected_count)
    score = max(transition_score, recovery_score)
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
            f"{' '.join(map(str, corrected_answers)) or '-'}. "
            f"Эталонных ответов по порядку: "
            f"{ordered_expected_count}/5"
        ),
    }


def _serial_score_from_count(correct_count: int) -> int:
    """Перевести число верных ответов в балл серийного счёта."""
    if correct_count >= 4:
        return 3
    if correct_count >= 2:
        return 2
    if correct_count == 1:
        return 1
    return 0


def _longest_serial_expected_subsequence(answers: list[int]) -> int:
    """Посчитать эталонные ответы, встреченные в нужном порядке."""
    previous_row = [0] * (len(SERIAL_EXPECTED) + 1)
    for answer in answers:
        current_row = [0]
        for index, expected in enumerate(SERIAL_EXPECTED, start=1):
            if answer == expected:
                current_row.append(previous_row[index - 1] + 1)
            else:
                current_row.append(
                    max(previous_row[index], current_row[index - 1])
                )
        previous_row = current_row
    return previous_row[-1]


def _normalize_fragmented_serial_numbers(text: str) -> str:
    """Склеить разорванные ASR числа вида «восемьдесят это шесть»."""
    normalized = text
    fillers = r"(?:это|(?:у\s+меня\s+)?будет|так|ну)"
    for tens_word in TENS:
        for unit_word in UNITS:
            normalized = re.sub(
                rf"(?<![а-я]){tens_word}\s+{fillers}\s+{unit_word}(?![а-я])",
                f"{tens_word} {unit_word}",
                normalized,
            )
    return normalized


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
    *,
    optional_asr_words: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Найти нужное предложение в непрерывной последовательности слов."""
    expected_words = _normalize_text(expected).split()
    actual_words = _normalize_text(transcript).split()
    expected_length = len(expected_words)
    matching_start: int | None = None
    for start in range(len(actual_words) - expected_length + 1):
        candidate = actual_words[start : start + expected_length]
        if all(
            _same_word_with_different_ending(expected_word, actual_word)
            for expected_word, actual_word in zip(expected_words, candidate)
        ):
            matching_start = start
            break

    matched_with_asr_tolerance = (
        matching_start is None
        and _sentence_matches_after_asr_correction(
            expected_words,
            actual_words,
            optional_asr_words,
        )
    )
    correct = matching_start is not None or matched_with_asr_tolerance
    if matching_start is not None:
        ignored_before = matching_start or 0
        ignored_after = len(actual_words) - ignored_before - expected_length
        details = (
            "Найдена непрерывная последовательность слов; "
            f"пропущено комментариев до: {ignored_before}, "
            f"после: {ignored_after}."
        )
    elif matched_with_asr_tolerance:
        details = (
            "Предложение совпало после коррекции типичных ошибок ASR "
            "в служебных словах, окончаниях или известных заменах."
        )
    elif len(actual_words) < expected_length:
        details = (
            "Количество слов не совпало: "
            f"ожидалось {len(expected_words)}, распознано {len(actual_words)}."
        )
    else:
        details = (
            "Не совпали слова: нужная непрерывная "
            "последовательность не найдена."
        )
    return {
        **base,
        "score": 1 if correct else 0,
        "max_score": 1,
        "status": "correct" if correct else "incorrect",
        "expected": expected,
        "details": details,
    }


def _sentence_matches_after_asr_correction(
    expected_words: list[str],
    actual_words: list[str],
    optional_words: tuple[str, ...],
) -> bool:
    """Проверить всё предложение после узких исправлений ошибок ASR.

    В этом резервном режиме комментарии внутри или снаружи не пропускаются:
    после удаления разрешённых служебных слов длина и порядок остальных слов
    должны полностью совпасть.
    """
    optional = set(optional_words)
    expected_content = [
        word for word in expected_words if word not in optional
    ]
    actual_content = [
        SENTENCE_ASR_WORD_REPLACEMENTS.get(word, word)
        for word in actual_words
        if word not in optional
    ]
    if len(expected_content) != len(actual_content):
        return False
    return all(
        _same_word_with_asr_tolerance(expected_word, actual_word)
        for expected_word, actual_word in zip(
            expected_content,
            actual_content,
        )
    )


def _same_word_with_asr_tolerance(expected: str, actual: str) -> bool:
    """Сравнить слово с дополнительным допуском для коротких окончаний."""
    if _same_word_with_different_ending(expected, actual):
        return True
    common_prefix_length = 0
    for expected_char, actual_char in zip(expected, actual):
        if expected_char != actual_char:
            break
        common_prefix_length += 1
    return (
        common_prefix_length >= 3
        and len(expected) - common_prefix_length <= 2
        and len(actual) - common_prefix_length <= 2
    )


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
    exact_phrases: tuple[str, ...] = (),
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
        matched_rule = next(
            (
                phrase
                for phrase in exact_phrases
                if _normalize_text(phrase) in normalized
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

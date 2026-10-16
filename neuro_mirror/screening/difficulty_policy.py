"""Подстройка уровня сложности под результаты занятий.

Курс устроен так: по итогам скрининга человек получает занятие из десяти игр
по своим доменам и первые дни проходит их на первом уровне. Если задание даётся
легко, уровень поднимается — иначе занятие перестаёт тренировать.

Правило намеренно осторожное. Уровень поднимается не после одной удачной
попытки, а когда успех повторился и человек провёл на уровне не меньше
нескольких дней: разовый хороший результат может объясняться удачным днём, а
не возросшей способностью. Понижение предусмотрено по той же причине с другой
стороны — адаптация, которая умеет только усложнять, однажды оставит человека
на непосильном уровне и будет фиксировать провал за провалом.

Уровни и параметры заданий заданы матрицей игр: уровень здесь только
выбирается, а что он означает для конкретной игры — дело самой игры.

Пороги требуют утверждения методистом: в матрице правил перехода между
уровнями нет, и числа ниже — предложение, а не норматив.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

MIN_LEVEL = 1
MAX_LEVEL = 3

# Сколько дней человек остаётся на уровне, прежде чем его можно поднять.
MIN_DAYS_AT_LEVEL = 2
# Сколько подряд успешных прохождений подтверждают, что уровень лёгок.
SUCCESSES_TO_PROMOTE = 2
# Сколько подряд неудачных прохождений говорят, что уровень непосилен.
FAILURES_TO_DEMOTE = 2

# Доля верных действий, выше которой задание считается лёгким.
EASY_RATE = 0.85
# Доля, ниже которой задание считается непосильным.
HARD_RATE = 0.40

# Какой показатель у какой игры означает долю успеха. Соответствие задаётся
# явно: подбор по совпадению имён однажды уже дал молчаливое расхождение, а
# пустая доля здесь означала бы, что уровень не меняется вообще.
SUCCESS_RATE_METRICS: dict[str, str] = {
    "GM-01": "u08_completion_rate",
    "GM-02": "m08_series_accuracy",
    "GM-03": "u01_correct_action_rate",
    "GM-04": "m07_target_recognition_rate",
    "GM-05": "m07_target_recognition_rate",
    "GM-06": "m08_series_accuracy",
    "GM-07": "u01_correct_action_rate",
    "GM-11": "e08_calculation_accuracy",
    "GM-12": "u01_correct_action_rate",
    "GM-15": "u01_correct_action_rate",
    "GM-09": "a06_tracking_accuracy",
    "GM-10": "a07_found_difference_rate",
    "GM-14": "u01_first_attempt_word_accuracy",
    "GM-17": "u01_correct_action_rate",
    "GM-18": "u08_completion_rate",
    "GM-20": "u01_correct_action_rate",
    "GM-21": "u01_correct_action_rate",
    "GM-23": "u01_correct_action_rate",
    "GM-24": "u01_correct_action_rate",
}


def _balanced_inhibition_rate(metrics: dict[str, Any]) -> float | None:
    """GM-08: одинаково учитывать пропуски Go и ответы на No-Go."""
    omission = metrics.get("g07_omission_rate")
    false_alarm = metrics.get("g08_false_alarm_rate")
    if not isinstance(omission, (int, float)) or not isinstance(false_alarm, (int, float)):
        return None
    return 1.0 - (float(omission) + float(false_alarm)) / 2.0


def _verbal_fluency_precision(metrics: dict[str, Any]) -> float | None:
    """GM-13/16: доля уникальных слов, соответствующих заданному правилу.

    Абсолютное число слов сохраняется отдельно: норматив продуктивности для
    автоматического перехода между уровнями должен быть утверждён после пилота.
    """
    valid = metrics.get("l04_valid_word_count")
    repetitions = metrics.get("l05_repetition_count")
    errors = metrics.get("l06_category_error_count", metrics.get("l06_rule_error_count"))
    if not all(isinstance(value, (int, float)) for value in (valid, repetitions, errors)):
        return None
    total = float(valid) + float(repetitions) + float(errors)
    return float(valid) / total if total > 0 else None


def _maze_route_rate(metrics: dict[str, Any]) -> float | None:
    """GM-19: качество пути с небольшим штрафом за каждый выход за границу."""
    redundancy = metrics.get("v02_path_redundancy")
    boundary_exits = metrics.get("v03_boundary_exits")
    if not isinstance(redundancy, (int, float)) or not isinstance(boundary_exits, (int, float)):
        return None
    return 1.0 / (1.0 + max(0.0, float(redundancy)) + 0.1 * max(0.0, float(boundary_exits)))


def _tower_rate(metrics: dict[str, Any]) -> float | None:
    """Близость решения башни к оптимальному.

    Готовой доли у этой игры нет: успех выражается тем, насколько число ходов
    превысило минимально необходимое.
    """
    valid = metrics.get("valid_move_count")
    above = metrics.get("e01_moves_above_optimum")
    if not isinstance(valid, (int, float)) or valid <= 0:
        return None
    if not isinstance(above, (int, float)):
        return None
    return max(0.0, min(1.0, (valid - above) / valid))


# Игры, у которых доля считается не одним показателем, а выражением.
DERIVED_RATES = {
    "GM-08": _balanced_inhibition_rate,
    "GM-13": _verbal_fluency_precision,
    "GM-16": _verbal_fluency_precision,
    "GM-19": _maze_route_rate,
    "GM-22": _tower_rate,
}


def has_levels(game_code: str) -> bool:
    """Задаёт ли матрица игр уровни сложности для этой формы."""
    return game_code in SUCCESS_RATE_METRICS or game_code in DERIVED_RATES


def success_rate(game_code: str, metrics: dict[str, Any]) -> float | None:
    """Доля успеха за одно прохождение, либо None, если её не определить."""
    derived = DERIVED_RATES.get(game_code)
    if derived is not None:
        return derived(metrics)

    key = SUCCESS_RATE_METRICS.get(game_code)
    if not key:
        return None
    raw = metrics.get(key)
    if not isinstance(raw, (int, float)):
        return None
    return max(0.0, min(1.0, float(raw)))


def classify(game_code: str, outcome: dict[str, Any]) -> str:
    """Отнести прохождение к лёгкому, посильному или непосильному.

    Технически непригодное прохождение не оценивается: сорванная запись или
    отказ оборудования не говорят ни о способностях человека, ни о сложности
    задания.
    """
    metrics = outcome.get("metrics") or {}
    if outcome.get("technical_validity") == "invalid":
        return "unknown"
    if outcome.get("completion_status") == "incomplete":
        return "hard"
    rate = success_rate(game_code, metrics)
    if rate is None:
        return "unknown"
    if rate >= EASY_RATE:
        return "easy"
    if rate < HARD_RATE:
        return "hard"
    return "suitable"


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def next_level(
    game_code: str,
    history: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> int:
    """Уровень, на котором игру следует предъявить в следующий раз.

    ``history`` — прохождения этой игры этим человеком, в любом порядке;
    каждое содержит уровень, время и исход.
    """
    if not has_levels(game_code):
        return MIN_LEVEL

    moment = (now or datetime.now(UTC)).astimezone(UTC)
    passes = []
    for item in history:
        at = _as_datetime(item.get("presented_at"))
        if at is None:
            continue
        level = item.get("difficulty_level")
        passes.append((at, int(level) if isinstance(level, int) else MIN_LEVEL, item))
    if not passes:
        return MIN_LEVEL

    passes.sort(key=lambda row: row[0])
    current = passes[-1][1]
    at_current = [row for row in passes if row[1] == current]

    verdicts = [classify(game_code, row[2]) for row in at_current]
    judged = [v for v in verdicts if v != "unknown"]

    # Понижение не ждёт выдержки по времени: оставлять человека на непосильном
    # уровне ради срока бессмысленно.
    if current > MIN_LEVEL and len(judged) >= FAILURES_TO_DEMOTE:
        if all(v == "hard" for v in judged[-FAILURES_TO_DEMOTE:]):
            return current - 1

    if current >= MAX_LEVEL:
        return MAX_LEVEL
    if len(judged) < SUCCESSES_TO_PROMOTE:
        return current
    if not all(v == "easy" for v in judged[-SUCCESSES_TO_PROMOTE:]):
        return current

    first_at_level = at_current[0][0]
    if moment - first_at_level < timedelta(days=MIN_DAYS_AT_LEVEL):
        return current
    return current + 1


def explain(game_code: str, history: Iterable[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Расшифровка решения для отчёта специалиста."""
    items = list(history)
    level = next_level(game_code, items, now=now)
    verdicts = [classify(game_code, item) for item in items]
    return {
        "game_code": game_code,
        "has_levels": has_levels(game_code),
        "next_level": level,
        "passes": len(items),
        "verdicts": verdicts,
    }

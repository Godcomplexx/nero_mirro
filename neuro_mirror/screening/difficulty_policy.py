"""Уровень сложности формы по «Методике подбора и оценки тренировочного курса».

Правило взято из методики v2 от 08.10.2026, раздел 6; номера пунктов ниже
ссылаются на неё. Методика ещё на утверждении: значения с пометкой
«предложение» в ней — предложения, а не утверждённые нормативы.

Уровень ведётся отдельно для каждой формы (6.1). Переход по итогам одного
учитываемого прохождения (6.3):

* успешность не ниже 0,85 — уровень +1;
* от 0,50 до 0,85 — уровень сохраняется;
* ниже 0,50 два учитываемых прохождения подряд — уровень −1.

Когда правило применяется — номер занятия, присвоение уровня перед 6-м
занятием — решает курс (``training_course``), здесь только сам переход.

Успешность — числитель и знаменатель, а не доля: порог проверяется точно,
``верные · 100 ≥ 85 · всего`` (6.2). Доля с плавающей точкой на границе
даёт 0,8499… и молча не поднимает уровень.

Уровни и параметры заданы матрицей игр: здесь уровень только выбирается, а что
он означает для конкретной игры — дело самой игры.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MIN_LEVEL = 1
MAX_LEVEL = 3

# Пороги перехода в процентах (6.3).
PROMOTE_PERCENT = 85
DEMOTE_PERCENT = 50
# Сколько прохождений ниже порога подряд понижают уровень.
FAILURES_TO_DEMOTE = 2

# Отметки формы (6.3, граничные случаи; предложение методики).
FLAG_HARD = "трудная"
FLAG_CEILING = "потолок"
# Форма без уровней в матрице: уровень не ведётся, правило не запускается.
FIXED_CONFIG = "fixed_config"
ADAPTIVE = "adaptive"

# Статусы завершения, которые учитываются в адаптации (6.2). Игры отдают
# «completed», когда пройдены все пробы, и «incomplete», когда задание
# кончилось раньше — по времени или попыткам. Прерванное пользователем задание
# отчёта не даёт вовсе и сюда не попадает.
COUNTED_COMPLETION = frozenset({"completed", "incomplete"})

# Показатель успешности каждой формы — числитель и знаменатель (раздел 7).
# Соответствие задано явно: подбор по совпадению имён однажды уже дал
# молчаливое расхождение, а пустая успешность здесь означала бы, что уровень
# не меняется вообще.
SUCCESS_COUNTS: dict[str, tuple[str, str]] = {
    "GM-01": ("u08_pairs_found", "u08_pairs_total"),
    "GM-02": ("m08_correct_series", "m08_series_total"),
    "GM-03": ("u01_correct_actions", "u01_actions_total"),
    "GM-04": ("m07_recognized_targets", "m07_targets_total"),
    "GM-06": ("m08_correct_series", "m08_series_total"),
    "GM-07": ("u01_correct_actions", "u01_actions_total"),
    "GM-09": ("a06_tracked_targets", "a06_targets_total"),
    "GM-10": ("a07_found_differences", "a07_differences_total"),
    "GM-14": ("u01_first_attempt_words", "u01_words_total"),
    "GM-17": ("u01_correct_actions", "u01_actions_total"),
    "GM-18": ("u01_first_attempt_pieces", "u01_pieces_total"),
    "GM-22": ("u03_target_towers", "u03_towers_total"),
}


@dataclass(frozen=True, slots=True)
class Success:
    """Успешность одного или нескольких прохождений: верные из всех."""

    correct: int
    total: int

    def at_least(self, percent: int) -> bool:
        return self.correct * 100 >= percent * self.total

    def __add__(self, other: "Success") -> "Success":
        return Success(self.correct + other.correct, self.total + other.total)

    def to_dict(self) -> dict[str, int]:
        return {"correct": self.correct, "total": self.total}


@dataclass(frozen=True, slots=True)
class FormState:
    """Уровень формы и то, что нужно для следующего перехода."""

    level: int = MIN_LEVEL
    # Учитываемые прохождения ниже 0,50 подряд; сбрасывается при смене уровня.
    below_half_streak: int = 0
    flags: frozenset[str] = field(default_factory=frozenset)


def has_levels(game_code: str) -> bool:
    """Задаёт ли матрица игр уровни сложности для этой формы."""
    return game_code in SUCCESS_COUNTS


def adaptation(game_code: str) -> str:
    return ADAPTIVE if has_levels(game_code) else FIXED_CONFIG


def success(game_code: str, metrics: dict[str, Any]) -> Success | None:
    """Успешность прохождения, либо None, если её не определить."""
    keys = SUCCESS_COUNTS.get(game_code)
    if keys is None:
        return None
    correct, total = (metrics.get(key) for key in keys)
    if isinstance(correct, bool) or isinstance(total, bool):
        return None
    if not isinstance(correct, int) or not isinstance(total, int):
        return None
    if total <= 0 or not 0 <= correct <= total:
        return None
    return Success(correct, total)


def counted_success(game_code: str, outcome: dict[str, Any]) -> Success | None:
    """Успешность прохождения, если оно учитывается в адаптации (6.2).

    Технически непригодное прохождение не учитывается: сорванная запись или
    отказ оборудования не говорят ни о способностях человека, ни о сложности
    задания. Не учитывается и прохождение без показателей полноты.
    """
    if outcome.get("technical_validity") != "valid":
        return None
    if outcome.get("completion_status") not in COUNTED_COMPLETION:
        return None
    return success(game_code, outcome.get("metrics") or {})


def apply_pass(state: FormState, result: Success) -> FormState:
    """Состояние формы после одного учитываемого прохождения (6.3).

    За один пересчёт уровень меняется не больше чем на шаг.
    """
    if result.at_least(PROMOTE_PERCENT):
        if state.level < MAX_LEVEL:
            return FormState(level=state.level + 1)
        return FormState(level=MAX_LEVEL, flags=frozenset({FLAG_CEILING}))

    if result.at_least(DEMOTE_PERCENT):
        return FormState(level=state.level)

    streak = state.below_half_streak + 1
    if streak < FAILURES_TO_DEMOTE:
        return FormState(level=state.level, below_half_streak=streak, flags=state.flags - {FLAG_CEILING})
    if state.level > MIN_LEVEL:
        return FormState(level=state.level - 1)
    # Ниже уровня 1 опускаться некуда: форма отмечается как трудная, а
    # серия продолжается — следующий провал снова подтвердит отметку.
    return FormState(level=MIN_LEVEL, below_half_streak=streak, flags=frozenset({FLAG_HARD}))


# Присвоение уровня перед 6-м занятием (6.3, п. 2; предложение методики).
ASSIGN_LEVEL_2_PERCENT = 85
ASSIGN_LAST_PASS_PERCENT = 70
ASSIGN_HARD_PERCENT = 50


def assign_level(results: list[Success]) -> FormState:
    """Уровень, с которым форма идёт в 6-м занятии, по занятиям 3–5.

    ``results`` — учитываемые прохождения формы в порядке показа. Уровень 2
    получает форма со сводной успешностью не ниже 0,85, у которой последнее
    прохождение не ниже 0,70: результат к концу освоения не падает.
    """
    if not results:
        return FormState()
    total = Success(0, 0)
    for item in results:
        total = total + item
    if total.at_least(ASSIGN_LEVEL_2_PERCENT) and results[-1].at_least(ASSIGN_LAST_PASS_PERCENT):
        return FormState(level=2)
    if not total.at_least(ASSIGN_HARD_PERCENT):
        return FormState(flags=frozenset({FLAG_HARD}))
    return FormState()


def describe(state: FormState) -> dict[str, Any]:
    return {
        "level": state.level,
        "below_half_streak": state.below_half_streak,
        "flags": sorted(state.flags),
    }

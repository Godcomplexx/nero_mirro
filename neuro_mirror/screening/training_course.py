"""Курс тренировок: 12 занятий, этапы, стимульные наборы и уровни форм.

Курс задаётся «Методикой подбора и оценки тренировочного курса», черновик v2
от 08.10.2026 (на утверждении); номера разделов ниже ссылаются на неё.
Полное описание и состояние каждого правила — docs/training-course.md.

Здесь только правила, без хранения: что за этап у занятия с данным номером,
какой стимульный набор в нём показывать и на каком уровне идёт каждая форма.
Уровни не хранятся отдельно, а каждый раз выводятся из прохождений курса —
так сохранённое состояние не может разойтись с тем, что человек проходил.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from neuro_mirror.plugins.games.contracts import GameDefinition
from neuro_mirror.screening.difficulty_policy import (
    FormState,
    Success,
    apply_pass,
    assign_level,
    describe,
    has_levels,
)

COURSE_SESSIONS = 12


@dataclass(frozen=True, slots=True)
class Stage:
    id: str
    title: str
    first: int
    last: int

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "sessions": [self.first, self.last]}


# Этапы курса (4.3).
STAGES: tuple[Stage, ...] = (
    Stage("calibration", "Калибровка", 1, 2),
    Stage("mastering", "Освоение", 3, 5),
    Stage("assignment", "Присвоение уровней и промежуточный контроль", 6, 6),
    Stage("adaptive", "Адаптивная тренировка", 7, COURSE_SESSIONS),
)

# Занятия, по которым присваивается уровень перед 6-м (6.3, п. 2).
ASSIGNMENT_SESSIONS = range(3, 6)
ASSIGNMENT_BEFORE = 6


def stage_for(session_number: int) -> Stage:
    for stage in STAGES:
        if stage.first <= session_number <= stage.last:
            return stage
    raise ValueError(f"В курсе {COURSE_SESSIONS} занятий, занятия {session_number} нет.")


def stimulus_set_number(session_number: int) -> int:
    """Номер стимульного набора в занятии (6.5).

    Калибровка — набор 1, освоение — набор 2, 6-е занятие — набор 3, ранее
    не показанный; занятия 7–11 — наборы 1 и 2 по очереди; 12-е — снова
    набор 3, чтобы сравнить с 6-м на том же материале.
    """
    stage = stage_for(session_number)
    if stage.id == "calibration":
        return 1
    if stage.id == "mastering":
        return 2
    if session_number in (ASSIGNMENT_BEFORE, COURSE_SESSIONS):
        return 3
    return 1 if session_number % 2 == 1 else 2


def stimulus_set_for(definition: GameDefinition, session_number: int) -> tuple[str, int]:
    """Название набора формы и его номер по курсу.

    У формы с одним набором он показывается всегда, а различаются занятия
    зерном случайности. Если наборов меньше трёх, номера идут по кругу.
    """
    number = stimulus_set_number(session_number)
    sets = definition.stimulus_sets
    if not sets:
        return "", number
    return sets[(number - 1) % len(sets)], number


def randomization_seed(user_id: str, game_code: str, session_number: int) -> int:
    """Зерно случайности «пользователь + форма + номер занятия» (6.5)."""
    digest = hashlib.sha256(f"{user_id}|{game_code}|{session_number}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


@dataclass(frozen=True, slots=True)
class CoursePass:
    """Прохождение формы в курсе; ``result`` пуст, если оно не учитывается."""

    session_number: int
    game_code: str
    result: Success | None


def form_states(
    passes: Iterable[CoursePass],
    session_number: int,
) -> tuple[dict[str, FormState], list[dict[str, Any]]]:
    """Уровни форм перед занятием ``session_number`` и журнал переходов.

    ``passes`` идут в порядке показа. Форма, которой нет в ответе, идёт на
    уровне 1 без отметок.

    * Занятия 1–5 — у всех форм уровень 1.
    * Перед 6-м уровень присваивается по занятиям 3–5; калибровка (1–2) в
      присвоение не входит.
    * Перед 7-м и далее — переход по итогам каждого учитываемого прохождения
      начиная с 6-го занятия. Форма, которой в занятии не было, уровень не
      меняет.
    """
    states: dict[str, FormState] = {}
    log: list[dict[str, Any]] = []
    if session_number <= ASSIGNMENT_BEFORE - 1:
        return states, log

    counted = [item for item in passes if item.result is not None and has_levels(item.game_code)]

    by_form: dict[str, list[Success]] = {}
    for item in counted:
        if item.session_number in ASSIGNMENT_SESSIONS:
            by_form.setdefault(item.game_code, []).append(item.result)
    for code, results in by_form.items():
        state = assign_level(results)
        states[code] = state
        total = Success(0, 0)
        for result in results:
            total = total + result
        log.append({
            "before_session": ASSIGNMENT_BEFORE,
            "game_code": code,
            "kind": "assignment",
            "from_level": 1,
            **_state_fields(state),
            "success": total.to_dict(),
            "last_success": results[-1].to_dict(),
        })

    for item in counted:
        if not ASSIGNMENT_BEFORE <= item.session_number < session_number:
            continue
        before = states.get(item.game_code, FormState())
        after = apply_pass(before, item.result)
        states[item.game_code] = after
        if after.level != before.level or after.flags != before.flags:
            log.append({
                "before_session": item.session_number + 1,
                "game_code": item.game_code,
                "kind": "transition",
                "from_level": before.level,
                **_state_fields(after),
                "success": item.result.to_dict(),
            })
    return states, log


def _state_fields(state: FormState) -> dict[str, Any]:
    fields = describe(state)
    return {"to_level": fields["level"], "flags": fields["flags"]}

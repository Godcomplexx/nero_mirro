"""Порядок заданий в занятии («Методика подбора и оценки тренировочного курса» v2, 4.4).

Формы занятия уже подобраны (``training_session``); здесь решается только,
в каком порядке они идут. Из всех порядков берётся порядок с наименьшим
взвешенным числом нарушений желательных правил. При равенстве решает зерно
занятия, записанное в план, а каждое нарушение выбранного порядка пишется в
план — специалист его видит.

Желательные правила по убыванию веса (4.4):

1. не больше трёх заданий подряд с одним типом ответа;
2. не больше трёх подряд с одинаковой визуальной схемой выбора — **не
   проверяется**: в каталоге игр нет признака «схема выбора», а угадывать его
   по названию игры нельзя; правило записывается в план как непроверенное;
3. после сложного задания — более простое или другое по модальности;
   «сложное» — уровень 3 или успешность ниже 0,50 в прошлый раз (предложение
   методики);
4. два задания одного домена не стоят подряд;
5. модальности подачи чередуются.

Числовых весов методика не задаёт, только их порядок; веса ниже — решение
команды (5, 4, 3, 2, 1), менять здесь.

Закреплённые места:

* калибровка (занятия 1–2) начинается с простой формы — клик и зрительная
  подача (5.2, п. 4);
* с 3-го занятия первое и последнее задания — посильные: формы с наибольшей
  недавней успешностью (4.4, «Начало и конец занятия»; предложение методики).
  Недавняя успешность — последнее учитываемое прохождение формы в курсе.

Порядков 10! — их не перебирают по одному: стоимость порядка складывается из
пар соседних заданий и длины текущей серии одного типа ответа, поэтому
лучший порядок находится динамическим программированием по подмножествам
(2¹⁰ подмножеств × последнее задание × длина серии).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from neuro_mirror.plugins.games.contracts import GameDefinition, Modality, ResponseType
from neuro_mirror.screening.difficulty_policy import (
    DEMOTE_PERCENT,
    MAX_LEVEL,
    FormState,
    Success,
    has_levels,
)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    weight: int
    text: str


RESPONSE_RUN = Rule("response_run", 5, "Больше трёх заданий подряд с одним типом ответа")
SELECTION_SCHEME = Rule("selection_scheme", 4, "Больше трёх заданий подряд с одной визуальной схемой выбора")
AFTER_HARD = Rule("after_hard", 3, "После сложного задания — снова сложное с той же модальностью подачи")
SAME_DOMAIN = Rule("same_domain", 2, "Два задания одного домена подряд")
SAME_MODALITY = Rule("same_modality", 1, "Модальность подачи не чередуется")

MAX_RUN = 3
NOT_CHECKED = (
    f"{SELECTION_SCHEME.text}: в каталоге игр нет признака «схема выбора».",
)

# С какого занятия первое и последнее задания — посильные
FEASIBLE_FROM_SESSION = 3
CALIBRATION_SESSIONS = (1, 2)

RESPONSE_LABELS = {
    ResponseType.CLICK: "клик",
    ResponseType.DRAG: "перетаскивание",
    ResponseType.POINTER: "ведение курсора",
    ResponseType.SPOKEN: "голос",
}


def is_simple_start(definition: GameDefinition) -> bool:
    """Форма, с которой начинается калибровка (5.2, п. 4): клик и только
    зрительная подача; голос, перетаскивание и ведение курсора первыми не
    ставятся."""
    return (
        definition.response_type == ResponseType.CLICK
        and set(definition.modalities) == {Modality.VISUAL}
    )


def is_hard(code: str, states: dict[str, FormState], recent: dict[str, Success]) -> bool:
    """«Сложное» задание (4.4, правило 3): уровень 3 или успешность ниже 0,50
    в прошлый раз. У формы без уровней сложность не ведётся."""
    if not has_levels(code):
        return False
    state = states.get(code, FormState())
    last = recent.get(code)
    return state.level >= MAX_LEVEL or (last is not None and not last.at_least(DEMOTE_PERCENT))


def _better(left: Success, right: Success) -> bool:
    """Успешность ``left`` выше ``right`` — точно, перекрёстным умножением."""
    return left.correct * right.total > right.correct * left.total


def arrange(
    games: list[dict[str, Any]],
    definitions: dict[str, GameDefinition],
    *,
    session_number: int,
    seed: int,
    states: dict[str, FormState] | None = None,
    recent: dict[str, Success] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Упорядочить формы занятия; вернуть порядок и запись для плана."""
    states = states or {}
    recent = recent or {}
    count = len(games)
    note: dict[str, Any] = {
        "seed": seed,
        "cost": 0,
        "violations": [],
        "not_checked": list(NOT_CHECKED),
        "first": None,
        "last": None,
    }
    if count == 0:
        return [], note

    defs = [definitions[game["game_code"]] for game in games]
    responses = [item.response_type for item in defs]
    modalities = [frozenset(item.modalities) for item in defs]
    domains = [game["domain"] for game in games]
    hard = [is_hard(game["game_code"], states, recent) for game in games]

    # Зерно решает при равенстве: кандидаты перебираются в его порядке, и
    # из равных по стоимости берётся первый.
    rank = list(range(count))
    random.Random(seed).shuffle(rank)

    first_allowed: list[int] = rank[:]
    last_fixed: int | None = None
    feasible_first = False
    if session_number in CALIBRATION_SESSIONS:
        simple = [index for index in rank if is_simple_start(defs[index])]
        if simple:
            first_allowed = simple
            note["first"] = {
                "game_code": games[simple[0]]["game_code"],
                "reason": "калибровка начинается с простой формы: клик и зрительная подача",
            }
    elif session_number >= FEASIBLE_FROM_SESSION:
        feasible = [index for index in rank if games[index]["game_code"] in recent]
        # Устойчивая сортировка по убыванию успешности: равные остаются в
        # порядке зерна.
        ordered: list[int] = []
        for index in feasible:
            position = next(
                (i for i, other in enumerate(ordered)
                 if _better(recent[games[index]["game_code"]], recent[games[other]["game_code"]])),
                len(ordered),
            )
            ordered.insert(position, index)
        if ordered:
            first_allowed = [ordered[0]]
            feasible_first = True
        if len(ordered) > 1 and count > 1:
            last_fixed = ordered[1]

    def pair_cost(a: int, b: int) -> int:
        cost = 0
        if hard[a] and hard[b] and modalities[a] == modalities[b]:
            cost += AFTER_HARD.weight
        if domains[a] == domains[b]:
            cost += SAME_DOMAIN.weight
        if modalities[a] == modalities[b]:
            cost += SAME_MODALITY.weight
        return cost

    full = (1 << count) - 1

    @lru_cache(maxsize=None)
    def best(mask: int, last: int, run: int) -> int:
        if mask == full:
            return 0
        result = None
        for b in rank:
            if mask & (1 << b):
                continue
            if b == last_fixed and (mask | (1 << b)) != full:
                continue
            same = responses[b] == responses[last]
            next_run = min(run + 1, MAX_RUN + 1) if same else 1
            step = pair_cost(last, b) + (RESPONSE_RUN.weight if same and run >= MAX_RUN else 0)
            total = step + best(mask | (1 << b), b, min(next_run, MAX_RUN))
            if result is None or total < result:
                result = total
        return result if result is not None else 10 ** 9

    starts = [index for index in first_allowed if index != last_fixed or count == 1]
    start = min(starts, key=lambda index: best(1 << index, index, 1))
    order = [start]
    mask, run = 1 << start, 1
    total_cost = best(mask, start, 1)
    while mask != full:
        last = order[-1]
        target = best(mask, last, run)
        for b in rank:
            if mask & (1 << b):
                continue
            if b == last_fixed and (mask | (1 << b)) != full:
                continue
            same = responses[b] == responses[last]
            next_run = min(run + 1, MAX_RUN) if same else 1
            step = pair_cost(last, b) + (RESPONSE_RUN.weight if same and run >= MAX_RUN else 0)
            if step + best(mask | (1 << b), b, next_run) == target:
                order.append(b)
                mask |= 1 << b
                run = next_run
                break

    note["cost"] = total_cost
    note["violations"] = _violations(order, games, responses, modalities, domains, hard)
    if feasible_first:
        note["first"] = _feasible_note(games[order[0]]["game_code"], recent)
    if last_fixed is not None:
        note["last"] = _feasible_note(games[order[-1]]["game_code"], recent)
    return [games[index] for index in order], note


def _feasible_note(code: str, recent: dict[str, Success]) -> dict[str, Any]:
    return {
        "game_code": code,
        "reason": "посильная форма: наибольшая недавняя успешность",
        "success": recent[code].to_dict(),
    }


def _violations(
    order: list[int],
    games: list[dict[str, Any]],
    responses: list[ResponseType],
    modalities: list[frozenset[Modality]],
    domains: list[str],
    hard: list[bool],
) -> list[dict[str, Any]]:
    """Нарушения желательных правил в выбранном порядке — для плана занятия."""
    found: list[dict[str, Any]] = []

    def add(rule: Rule, positions: list[int], detail: str) -> None:
        found.append({
            "rule": rule.id,
            "weight": rule.weight,
            "text": rule.text,
            "positions": positions,
            "detail": detail,
        })

    run = 1
    for step in range(1, len(order)):
        a, b = order[step - 1], order[step]
        run = run + 1 if responses[b] == responses[a] else 1
        if run > MAX_RUN:
            add(RESPONSE_RUN, list(range(step - MAX_RUN + 1, step + 2)),
                f"{run}-е задание подряд с ответом «{RESPONSE_LABELS.get(responses[b], responses[b])}»")
        if hard[a] and hard[b] and modalities[a] == modalities[b]:
            add(AFTER_HARD, [step, step + 1], f"{games[a]['game_code']} → {games[b]['game_code']}")
        if domains[a] == domains[b]:
            add(SAME_DOMAIN, [step, step + 1], domains[a])
        if modalities[a] == modalities[b]:
            add(SAME_MODALITY, [step, step + 1], f"{games[a]['game_code']} → {games[b]['game_code']}")
    return found

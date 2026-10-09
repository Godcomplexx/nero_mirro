"""Готовое тренировочное занятие: от профиля MoCA до списка конкретных игр.

Сборка занятия целиком лежит в ядре, а не в интерфейсе. Интерфейс получает
упорядоченный список игр и просто проигрывает его: правило подбора, перевод
доменов в коды игр и защита от повторов остаются в одном месте.

Домены занятия идут вперемежку, а не блоками: четыре игры на внимание подряд
утомляют и сводят на нет чередование механик, которое обеспечивает подбор.

Занятие — часть курса из 12 (``training_course``): номер занятия задаёт этап,
стимульный набор и то, меняются ли уровни. Правила — «Методика подбора и
оценки тренировочного курса» v2, разделы 4.2–4.4, 5 и 6.5.
"""
from __future__ import annotations

from typing import Any, Iterable

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.plugins.games.contracts import Domain, GameDefinition, Modality, ResponseType
from neuro_mirror.plugins.games.selector import (
    CourseRanking,
    NoEligibleGameError,
    Presentation,
    select_game,
)
from neuro_mirror.screening.difficulty_policy import (
    FLAG_CEILING,
    FLAG_HARD,
    FormState,
    adaptation,
    has_levels,
)
from neuro_mirror.screening.moca_scoring import MOCA_MODULES
from neuro_mirror.screening.training_course import (
    randomization_seed,
    stage_for,
    stimulus_set_for,
)
from neuro_mirror.screening.training_plan import DEFAULT_SESSION_SIZE, plan_session

# Профиль называет домены по-русски, игры — кодами. Соответствие берётся из
# той же таблицы, что и сам профиль, чтобы названия не разошлись.
DOMAIN_CODES: dict[str, str] = {
    str(module["label"]): str(module["id"]) for module in MOCA_MODULES
}


def order_domains(plan: dict[str, int]) -> list[str]:
    """Порядок доменов в занятии: вперемежку, не блоками.

    На каждом шаге берётся домен с наибольшим остатком — так домен с четырьмя
    заданиями распределяется по всему занятию, а не идёт подряд.
    """
    remaining = {domain: int(count) for domain, count in plan.items() if int(count) > 0}
    order: list[str] = []
    positions = list(remaining)
    while remaining:
        # Тот же домен подряд берётся только когда других не осталось:
        # иначе домен с большим остатком выдал бы несколько игр кряду.
        candidates = [d for d in remaining if not order or d != order[-1]] or list(remaining)
        domain = max(
            candidates,
            key=lambda d: (remaining[d], -positions.index(d)),
        )
        order.append(domain)
        remaining[domain] -= 1
        if remaining[domain] == 0:
            del remaining[domain]
    return order


def _is_simple_start(definition: GameDefinition) -> bool:
    """Форма, с которой можно начинать калибровку (5.2, п. 4).

    Клик и только зрительная подача: голосовой ответ, перетаскивание и
    ведение курсора первыми не ставятся.
    """
    return (
        definition.response_type == ResponseType.CLICK
        and set(definition.modalities) == {Modality.VISUAL}
    )


def _start_with_simple_form(
    games: list[dict[str, Any]],
    definitions: dict[str, GameDefinition],
) -> None:
    """Поставить первой простую форму, не ставя рядом два задания домена."""
    if not games or _is_simple_start(definitions[games[0]["game_code"]]):
        return
    for index in range(1, len(games)):
        if not _is_simple_start(definitions[games[index]["game_code"]]):
            continue
        candidate = games[:]
        candidate[0], candidate[index] = candidate[index], candidate[0]
        domains = [game["domain"] for game in candidate]
        if all(left != right for left, right in zip(domains, domains[1:])):
            games[:] = candidate
            return


def build_training_session(
    profile: Iterable[dict[str, Any]],
    *,
    session_number: int = 1,
    user_id: str = "",
    history: tuple[Presentation, ...] = (),
    course_sessions: tuple[tuple[str, ...], ...] = (),
    domain_totals: dict[str, int] | None = None,
    states: dict[str, FormState] | None = None,
    available_codes: frozenset[str] | None = None,
    definitions: tuple[GameDefinition, ...] = GAME_CATALOG,
    session_size: int = DEFAULT_SESSION_SIZE,
) -> dict[str, Any]:
    """Собрать занятие курса: план по доменам плюс конкретные игры по порядку.

    ``course_sessions`` — коды форм прошлых занятий курса по порядку,
    ``domain_totals`` — сколько заданий каждого домена уже было в курсе,
    ``states`` — уровни форм перед этим занятием (``training_course.form_states``).
    """
    profile = list(profile)
    stage = stage_for(session_number)
    if not profile:
        return {"plan": {}, "games": [], "session_size": 0, "skipped": []}

    states = states or {}
    by_code = {item.code: item for item in definitions}
    plan = plan_session(profile, session_size=session_size, course_totals=domain_totals)

    mechanic_counts: dict[str, int] = {}
    for session_codes in course_sessions:
        for code in session_codes:
            definition = by_code.get(code)
            for mechanic in definition.mechanics if definition else ():
                mechanic_counts[mechanic] = mechanic_counts.get(mechanic, 0) + 1
    ranking = CourseRanking(
        adaptive_codes=frozenset(code for code in by_code if has_levels(code)),
        discouraged_codes=frozenset(
            code for code, state in states.items() if state.flags & {FLAG_HARD, FLAG_CEILING}
        ),
        mechanic_counts=mechanic_counts,
        previous_session_codes=frozenset(course_sessions[-1]) if course_sessions else frozenset(),
    )

    games: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    used_codes: set[str] = set()
    previous: GameDefinition | None = None

    for domain_label in order_domains(plan):
        code = DOMAIN_CODES.get(domain_label)
        if code is None:
            skipped.append({"domain": domain_label, "reason": "неизвестный домен"})
            continue
        try:
            decision = select_game(
                Domain(code),
                session_game_codes=frozenset(used_codes),
                history=history,
                available_codes=available_codes,
                definitions=definitions,
                previous=previous,
                course=ranking,
            )
        except NoEligibleGameError as exc:
            # Занятие не срывается из-за исчерпания форм одного домена:
            # остальные игры остаются, а пропуск виден в ответе.
            skipped.append({"domain": domain_label, "reason": str(exc)})
            continue
        game = decision.game
        used_codes.add(game.code)
        previous = game
        stimulus_set, set_number = stimulus_set_for(game, session_number)
        # У формы без уровней в матрице уровень не ведётся (6.3).
        state = states.get(game.code, FormState())
        games.append({
            "domain": domain_label,
            "domain_code": code,
            "game_code": game.code,
            "title": game.title,
            "stimulus_set": stimulus_set,
            "stimulus_set_number": set_number,
            "randomization_seed": randomization_seed(user_id, game.code, session_number),
            "difficulty_level": state.level if has_levels(game.code) else None,
            "adaptation": adaptation(game.code),
            "flags": sorted(state.flags),
            "reasons": list(decision.reasons),
        })

    if stage.id == "calibration":
        _start_with_simple_form(games, by_code)
    for position, game in enumerate(games, start=1):
        game["position"] = position

    return {
        "plan": plan,
        "games": games,
        "session_size": len(games),
        "skipped": skipped,
    }

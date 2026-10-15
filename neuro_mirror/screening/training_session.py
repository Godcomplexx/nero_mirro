"""Занятие курса тренировок: от профиля MoCA до списка конкретных игр.

Состав по доменам считается из входного профиля и во всех 12 занятиях один и
тот же. Конкретные формы (игры) подбираются заново к каждому занятию по
приоритетам «Методики подбора и оценки тренировочного курса» v2 (разделы 4.4,
5.2, 6.3): сначала формы с адаптацией, реже — с отметками «трудная» и
«потолок», затем механика, реже встречавшаяся в курсе, и форма, которой не
было в прошлом занятии. Так за калибровку охватываются все формы, а дальше
они чередуются. Уровень каждой формы и стимульный набор задаёт
``training_course``.

Сборка целиком лежит в ядре, а не в интерфейсе. Интерфейс получает
упорядоченный список игр и просто проигрывает его: правило подбора, перевод
доменов в коды игр и защита от повторов остаются в одном месте.

Формы подбираются по доменам вперемежку, а не блоками: так чередование
механик при подборе сравнивает соседние задания. Окончательный порядок
решает ``session_order``: из всех порядков подобранных форм — с наименьшим
взвешенным числом нарушений желательных правил 4.4, с посильными заданиями в
начале и в конце; нарушения пишутся в план.
"""
from __future__ import annotations

from typing import Any, Iterable

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.plugins.games.contracts import Domain, GameDefinition
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
    Success,
    adaptation,
    has_levels,
)
from neuro_mirror.screening.moca_scoring import MOCA_MODULES
from neuro_mirror.screening.session_order import arrange
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


def build_training_session(
    profile: Iterable[dict[str, Any]],
    *,
    session_number: int = 1,
    course_sessions: tuple[tuple[str, ...], ...] = (),
    states: dict[str, FormState] | None = None,
    recent: dict[str, Success] | None = None,
    order_seed: int = 0,
    history: tuple[Presentation, ...] = (),
    available_codes: frozenset[str] | None = None,
    definitions: tuple[GameDefinition, ...] = GAME_CATALOG,
    session_size: int = DEFAULT_SESSION_SIZE,
) -> dict[str, Any]:
    """Собрать занятие курса: план по доменам плюс конкретные игры по порядку.

    ``course_sessions`` — коды форм, показанных в прошлых занятиях курса, по
    порядку занятий; ``states`` — уровни и отметки форм перед этим занятием;
    ``recent`` — последняя учитываемая успешность каждой формы в курсе;
    ``order_seed`` — зерно, которое решает порядок при равенстве.
    """
    profile = list(profile)
    if not profile:
        return {"plan": {}, "games": [], "session_size": 0, "skipped": [], "order": None}

    states = states or {}
    by_code = {item.code: item for item in definitions}
    plan = plan_session(profile, session_size=session_size)
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
        games.append({
            "domain": domain_label,
            "domain_code": code,
            "game_code": game.code,
            "title": game.title,
            "adaptation": adaptation(game.code),
            "reasons": list(decision.reasons),
        })

    games, order = arrange(
        games,
        by_code,
        session_number=session_number,
        seed=order_seed,
        states=states,
        recent=recent,
    )
    for position, game in enumerate(games, start=1):
        game["position"] = position

    return {
        "plan": plan,
        "games": games,
        "session_size": len(games),
        "skipped": skipped,
        "order": order,
    }


def lighter_alternative(
    item: dict[str, Any],
    session_games: list[dict[str, Any]],
    *,
    states: dict[str, FormState] | None = None,
    history: tuple[Presentation, ...] = (),
    available_codes: frozenset[str] | None = None,
    definitions: tuple[GameDefinition, ...] = GAME_CATALOG,
) -> dict[str, Any] | None:
    """Облегчённая альтернатива прерванного задания (методика, 6.3, п. 3).

    Та же форма уровнем ниже, если её уровень выше первого; иначе другая
    форма того же домена, которой ещё не было в занятии, — на уровне 1.
    Уровень альтернативы временный: в сохранённый уровень формы он не
    записывается. Возвращает задание без номера и стимульного набора (их
    ставит курс) или None, если облегчить нечем.
    """
    states = states or {}
    level = item.get("difficulty_level")
    if isinstance(level, int) and level > 1:
        return {
            "domain": item["domain"],
            "domain_code": item["domain_code"],
            "game_code": item["game_code"],
            "title": item["title"],
            "adaptation": item.get("adaptation") or adaptation(item["game_code"]),
            "difficulty_level": level - 1,
            "reasons": ["облегчённая альтернатива: та же форма уровнем ниже"],
        }
    by_code = {definition.code: definition for definition in definitions}
    ranking = CourseRanking(
        adaptive_codes=frozenset(code for code in by_code if has_levels(code)),
        discouraged_codes=frozenset(
            code for code, state in states.items() if state.flags & {FLAG_HARD, FLAG_CEILING}
        ),
    )
    try:
        decision = select_game(
            Domain(item["domain_code"]),
            session_game_codes=frozenset(row["game_code"] for row in session_games),
            history=history,
            available_codes=available_codes,
            definitions=definitions,
            course=ranking,
        )
    except NoEligibleGameError:
        return None
    game = decision.game
    return {
        "domain": item["domain"],
        "domain_code": item["domain_code"],
        "game_code": game.code,
        "title": game.title,
        "adaptation": adaptation(game.code),
        "difficulty_level": 1 if has_levels(game.code) else None,
        "reasons": ["облегчённая альтернатива: другая форма того же домена", *decision.reasons],
    }

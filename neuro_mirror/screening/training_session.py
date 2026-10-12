"""Состав курса тренировок: от профиля MoCA до списка конкретных игр.

Состав собирается один раз, при открытии курса, и дальше не меняется: все 12
занятий проходят одни и те же задания в одном порядке. Меняются только
уровень каждой формы — по правильности её прохождений — и стимульный набор
по этапу курса (``training_course``).

Сборка целиком лежит в ядре, а не в интерфейсе. Интерфейс получает
упорядоченный список игр и просто проигрывает его: правило подбора, перевод
доменов в коды игр и защита от повторов остаются в одном месте.

Домены идут вперемежку, а не блоками: четыре игры на внимание подряд
утомляют и сводят на нет чередование механик, которое обеспечивает подбор.
"""
from __future__ import annotations

from typing import Any, Iterable

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.plugins.games.contracts import Domain, GameDefinition, Modality, ResponseType
from neuro_mirror.plugins.games.selector import (
    NoEligibleGameError,
    Presentation,
    select_game,
)
from neuro_mirror.screening.difficulty_policy import adaptation, has_levels
from neuro_mirror.screening.moca_scoring import MOCA_MODULES
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
    """Форма, с которой можно начинать занятие (методика, раздел 5.2, п. 4).

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
    history: tuple[Presentation, ...] = (),
    available_codes: frozenset[str] | None = None,
    definitions: tuple[GameDefinition, ...] = GAME_CATALOG,
    session_size: int = DEFAULT_SESSION_SIZE,
) -> dict[str, Any]:
    """Собрать состав курса: план по доменам плюс конкретные игры по порядку."""
    profile = list(profile)
    if not profile:
        return {"plan": {}, "games": [], "session_size": 0, "skipped": []}

    by_code = {item.code: item for item in definitions}
    adaptive_codes = frozenset(code for code in by_code if has_levels(code))
    plan = plan_session(profile, session_size=session_size)
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
                adaptive_codes=adaptive_codes,
            )
        except NoEligibleGameError as exc:
            # Курс не срывается из-за исчерпания форм одного домена:
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

    _start_with_simple_form(games, by_code)
    for position, game in enumerate(games, start=1):
        game["position"] = position

    return {
        "plan": plan,
        "games": games,
        "session_size": len(games),
        "skipped": skipped,
    }

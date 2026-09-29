"""Готовое тренировочное занятие: от профиля MoCA до списка конкретных игр.

Сборка занятия целиком лежит в ядре, а не в интерфейсе. Интерфейс получает
упорядоченный список игр и просто проигрывает его: правило подбора, перевод
доменов в коды игр и защита от повторов остаются в одном месте.

Домены занятия идут вперемежку, а не блоками: четыре игры на внимание подряд
утомляют и сводят на нет чередование механик, которое обеспечивает подбор.
"""
from __future__ import annotations

from typing import Any, Iterable

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.plugins.games.contracts import Domain, GameDefinition
from neuro_mirror.plugins.games.selector import (
    NoEligibleGameError,
    Presentation,
    select_game,
)
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


def build_training_session(
    profile: Iterable[dict[str, Any]],
    *,
    history: tuple[Presentation, ...] = (),
    available_codes: frozenset[str] | None = None,
    definitions: tuple[GameDefinition, ...] = GAME_CATALOG,
    session_size: int = DEFAULT_SESSION_SIZE,
) -> dict[str, Any]:
    """Собрать занятие: план по доменам плюс конкретные игры по порядку."""
    profile = list(profile)
    if not profile:
        return {"plan": {}, "games": [], "session_size": 0, "skipped": []}

    plan = plan_session(profile, session_size=session_size)
    games: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    used_codes: set[str] = set()
    used_sets: set[tuple[str, str]] = set()

    for position, domain_label in enumerate(order_domains(plan), start=1):
        code = DOMAIN_CODES.get(domain_label)
        if code is None:
            skipped.append({"domain": domain_label, "reason": "неизвестный домен"})
            continue
        try:
            decision = select_game(
                Domain(code),
                session_game_codes=frozenset(used_codes),
                session_stimulus_sets=frozenset(used_sets),
                history=history,
                available_codes=available_codes,
                definitions=definitions,
            )
        except NoEligibleGameError as exc:
            # Занятие не срывается из-за исчерпания форм одного домена:
            # остальные игры остаются, а пропуск виден в ответе.
            skipped.append({"domain": domain_label, "reason": str(exc)})
            continue
        used_codes.add(decision.game.code)
        used_sets.add((decision.game.code, decision.stimulus_set))
        games.append({
            "position": position,
            "domain": domain_label,
            "domain_code": code,
            "game_code": decision.game.code,
            "title": decision.game.title,
            "stimulus_set": decision.stimulus_set,
            "reasons": list(decision.reasons),
        })

    return {
        "plan": plan,
        "games": games,
        "session_size": len(games),
        "skipped": skipped,
    }

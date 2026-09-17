"""Сколько заданий каждого домена включить в тренировочное занятие.

Правило простое: чем больше баллов домен недобрал на скрининге, тем больше
заданий он получает. Недобор считается в баллах, а не в долях, — на грубой
шкале (абстракция даёт максимум 2 балла) доли всё равно принимают три-четыре
значения, а баллы читаются напрямую.

Две поправки не дают правилу развалиться:

* сумма недоборов по четырём доменам лежит в пределах от 0 до 15, а занятие
  фиксированной длины, поэтому остаток бюджета распределяется пропорционально,
  а не выдаётся один к одному;
* домен с полным баллом иначе выпал бы из занятия совсем, тогда как методика
  требует представительства всех доменов, поэтому каждому гарантирована хотя бы
  одна форма.
"""
from __future__ import annotations

from typing import Any, Iterable

DEFAULT_SESSION_SIZE = 10
DEFAULT_MIN_PER_DOMAIN = 1


def domain_shortfall(profile: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Недобранные баллы по каждому домену: M − S."""
    shortfall: dict[str, int] = {}
    for item in profile:
        domain = str(item.get("domain") or "")
        if not domain:
            continue
        maximum = int(item.get("max_score") or 0)
        score = max(0, min(int(item.get("score") or 0), maximum))
        shortfall[domain] = maximum - score
    return shortfall


def plan_session(
    profile: Iterable[dict[str, Any]],
    *,
    session_size: int = DEFAULT_SESSION_SIZE,
    min_per_domain: int = DEFAULT_MIN_PER_DOMAIN,
    max_per_domain: int | None = None,
) -> dict[str, int]:
    """Состав занятия: сколько заданий отдать каждому домену.

    Задания раздаются по одному: каждое следующее уходит домену с наибольшим
    отношением недобора к уже выданному. Так сильнее просевший домен получает
    больше, но по мере насыщения уступает очередь остальным, и ни один не
    забирает всё занятие. Сумма всегда равна ``session_size``.
    """
    shortfall = domain_shortfall(profile)
    if not shortfall:
        return {}

    domains = list(shortfall)
    guaranteed = min_per_domain * len(domains)
    if session_size < guaranteed:
        raise ValueError(
            f"Занятие из {session_size} заданий не вмещает по {min_per_domain} "
            f"на каждый из {len(domains)} доменов."
        )

    # Без ограничения сверху один домен при полном провале забрал бы почти всё
    # занятие, что противоречит чередованию механик и модальностей.
    cap = max_per_domain if max_per_domain is not None else max(min_per_domain, session_size // 2)
    if cap * len(domains) < session_size:
        raise ValueError(
            f"Предел {cap} заданий на домен не позволяет набрать занятие "
            f"из {session_size} заданий."
        )

    plan = {domain: min_per_domain for domain in domains}
    # При полностью пройденном скрининге веса равны: поддерживающий режим.
    total_shortfall = sum(shortfall.values())
    weights = (
        {domain: float(value) for domain, value in shortfall.items()}
        if total_shortfall
        else {domain: 1.0 for domain in domains}
    )

    for _ in range(session_size - guaranteed):
        available = [domain for domain in domains if plan[domain] < cap]
        if not available:
            break
        # При равных отношениях очередь у домена, получившего меньше заданий, —
        # иначе остаток целиком доставался бы первому домену списка.
        best = max(
            available,
            key=lambda d: (
                weights[d] / (plan[d] + 1),
                -plan[d],
                shortfall[d],
                -domains.index(d),
            ),
        )
        plan[best] += 1
    return plan


def explain_plan(
    profile: Iterable[dict[str, Any]],
    plan: dict[str, int],
) -> list[dict[str, Any]]:
    """Расшифровка состава занятия для отчёта специалиста."""
    shortfall = domain_shortfall(profile)
    rows = []
    for item in profile:
        domain = str(item.get("domain") or "")
        if domain not in plan:
            continue
        rows.append({
            "domain": domain,
            "score": item.get("score"),
            "max_score": item.get("max_score"),
            "shortfall": shortfall.get(domain, 0),
            "tasks": plan[domain],
        })
    return rows

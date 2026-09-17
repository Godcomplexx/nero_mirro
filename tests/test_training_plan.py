"""Состав тренировочного занятия по когнитивному профилю."""
from __future__ import annotations

import pytest

from neuro_mirror.screening.moca_scoring import COGNITIVE_DOMAINS
from neuro_mirror.screening.training_plan import (
    domain_shortfall,
    explain_plan,
    plan_session,
)

MEMORY, ATTENTION, SPEECH, ABSTRACTION = COGNITIVE_DOMAINS


def profile(memory: int, attention: int, speech: int, abstraction: int) -> list[dict]:
    pairs = ((MEMORY, memory, 5), (ATTENTION, attention, 5),
             (SPEECH, speech, 3), (ABSTRACTION, abstraction, 2))
    return [
        {"domain": name, "score": score, "max_score": maximum,
         "deficit": round((maximum - score) / maximum, 3)}
        for name, score, maximum in pairs
    ]


# ── Недобор ────────────────────────────────────────────────────────────────────

def test_shortfall_is_the_missing_points():
    assert domain_shortfall(profile(3, 5, 1, 0)) == {
        MEMORY: 2, ATTENTION: 0, SPEECH: 2, ABSTRACTION: 2,
    }


def test_shortfall_clamps_scores_above_the_maximum():
    assert domain_shortfall([{"domain": SPEECH, "score": 9, "max_score": 3}])[SPEECH] == 0


# ── Размер занятия ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("scores", [(0, 0, 0, 0), (5, 5, 3, 2), (3, 1, 2, 0), (5, 5, 0, 2)])
def test_session_always_has_the_requested_size(scores):
    plan = plan_session(profile(*scores))
    assert sum(plan.values()) == 10


@pytest.mark.parametrize("size", [4, 6, 9, 12, 16])
def test_session_size_is_respected_for_other_lengths(size):
    plan = plan_session(profile(2, 2, 1, 1), session_size=size)
    assert sum(plan.values()) == size


def test_session_smaller_than_the_domain_count_is_rejected():
    with pytest.raises(ValueError):
        plan_session(profile(0, 0, 0, 0), session_size=3)


# ── Представительство и предел ─────────────────────────────────────────────────

def test_every_domain_is_present_even_with_a_full_score():
    """Методика требует присутствия всех доменов в каждом занятии."""
    plan = plan_session(profile(5, 5, 3, 2))
    assert set(plan) == set(COGNITIVE_DOMAINS)
    assert all(count >= 1 for count in plan.values())


def test_single_domain_collapse_does_not_take_over_the_session():
    """Без предела один домен забрал бы почти всё занятие."""
    plan = plan_session(profile(5, 5, 0, 2))
    assert plan[SPEECH] == 5
    assert all(plan[d] >= 1 for d in COGNITIVE_DOMAINS)


def test_explicit_cap_is_honoured():
    plan = plan_session(profile(5, 5, 0, 2), max_per_domain=3)
    assert max(plan.values()) == 3
    assert sum(plan.values()) == 10


def test_cap_too_low_for_the_session_is_rejected():
    with pytest.raises(ValueError):
        plan_session(profile(0, 0, 0, 0), session_size=10, max_per_domain=2)


# ── Распределение ──────────────────────────────────────────────────────────────

def test_weaker_domain_gets_more_tasks():
    plan = plan_session(profile(0, 5, 3, 2))
    assert plan[MEMORY] > plan[ATTENTION]
    assert plan[MEMORY] > plan[SPEECH]


def test_equal_shortfall_gives_equal_share():
    plan = plan_session(profile(4, 4, 2, 1), session_size=8)
    assert plan[MEMORY] == plan[ATTENTION]
    assert plan[SPEECH] == plan[ABSTRACTION]


def test_full_score_spreads_evenly_instead_of_favouring_the_first_domain():
    """Поддерживающий режим: без недоборов остаток не должен доставаться одному."""
    plan = plan_session(profile(5, 5, 3, 2))
    assert max(plan.values()) - min(plan.values()) <= 1


def test_order_of_domains_follows_severity():
    plan = plan_session(profile(1, 3, 3, 2))
    assert plan[MEMORY] >= plan[ATTENTION] >= plan[SPEECH]


# ── Расшифровка ────────────────────────────────────────────────────────────────

def test_explanation_links_tasks_to_the_shortfall():
    data = profile(2, 5, 1, 2)
    rows = explain_plan(data, plan_session(data))
    by_domain = {row["domain"]: row for row in rows}
    assert by_domain[MEMORY]["shortfall"] == 3
    assert by_domain[MEMORY]["score"] == 2
    assert by_domain[MEMORY]["max_score"] == 5
    assert sum(row["tasks"] for row in rows) == 10


def test_empty_profile_gives_no_plan():
    assert plan_session([]) == {}

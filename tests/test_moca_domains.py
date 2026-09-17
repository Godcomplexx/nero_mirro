"""Когнитивный профиль по доменам и нормированный дефицит."""
from __future__ import annotations

import pytest

from neuro_mirror.screening.moca_scoring import (
    COGNITIVE_DOMAINS,
    TASK_DOMAINS,
    VOICE_MOCA_MAX_SCORE,
    domain_max_scores,
    summarize_domains,
    summarize_moca_tasks,
)


def _task(task_id: str, score: int) -> dict:
    return {"task_id": task_id, "score": score}


def _profile(tasks: list[dict]) -> dict[str, dict]:
    return {item["domain"]: item for item in summarize_domains(tasks)}


# ── Максимумы ──────────────────────────────────────────────────────────────────

def test_domain_maxima_match_the_method():
    assert domain_max_scores() == {
        "Память": 5,
        "Внимание": 5,
        "Речь": 3,
        "Абстракция": 2,
    }


def test_domain_maxima_sum_to_the_test_maximum():
    """Иначе профиль и общий балл говорили бы о разном."""
    assert sum(domain_max_scores().values()) == VOICE_MOCA_MAX_SCORE


def test_every_scored_task_belongs_to_a_domain():
    """Задание с баллом вне домена потерялось бы при расчёте профиля."""
    from neuro_mirror.plugins.moca_test.plugin import MOCA_TASKS
    from neuro_mirror.screening.moca_scoring import score_moca_task

    for task in MOCA_TASKS:
        has_points = score_moca_task(task.task_id, "")["max_score"] > 0
        assert has_points == (task.task_id in TASK_DOMAINS), task.task_id


def test_learning_trials_are_outside_the_profile():
    """Пробы заучивания фиксируются, но в балл и профиль не входят."""
    assert "memory_1" not in TASK_DOMAINS
    assert "memory_2" not in TASK_DOMAINS


# ── Дефицит ────────────────────────────────────────────────────────────────────

def test_full_score_gives_zero_deficit():
    tasks = [
        _task("delayed_recall", 5),
        _task("attention_digits_forward", 1),
        _task("attention_digits_backward", 1),
        _task("attention_serial", 3),
        _task("language_sentence_1", 1),
        _task("language_sentence_2", 1),
        _task("language_fluency", 1),
        _task("abstraction_1", 1),
        _task("abstraction_2", 1),
    ]
    profile = _profile(tasks)
    assert all(item["deficit"] == 0.0 for item in profile.values())
    assert profile["Внимание"]["score"] == 5


def test_no_answers_give_full_deficit():
    profile = _profile([_task(task_id, 0) for task_id in TASK_DOMAINS])
    assert all(item["deficit"] == 1.0 for item in profile.values())


def test_partial_score_gives_proportional_deficit():
    # Внимание: 2 из 5 → дефицит 0.6; Речь: 3 из 3 → дефицит 0
    tasks = [
        _task("attention_digits_forward", 1),
        _task("attention_digits_backward", 1),
        _task("attention_serial", 0),
        _task("language_sentence_1", 1),
        _task("language_sentence_2", 1),
        _task("language_fluency", 1),
    ]
    profile = _profile(tasks)
    assert profile["Внимание"]["score"] == 2
    assert profile["Внимание"]["deficit"] == pytest.approx(0.6)
    assert profile["Речь"]["deficit"] == 0.0


def test_missing_tasks_count_as_zero():
    """Прерванный тест не должен оставлять домен без оценки."""
    profile = _profile([_task("delayed_recall", 5)])
    assert profile["Память"]["deficit"] == 0.0
    assert profile["Внимание"]["score"] == 0
    assert profile["Внимание"]["deficit"] == 1.0


def test_learning_trials_do_not_add_points():
    profile = _profile([_task("memory_1", 5), _task("memory_2", 5)])
    assert profile["Память"]["score"] == 0


def test_unknown_task_is_ignored():
    profile = _profile([_task("что-то_новое", 4), _task("abstraction_1", 1)])
    assert profile["Абстракция"]["score"] == 1


def test_score_never_exceeds_the_domain_maximum():
    """Защита от повторного учёта задания при возобновлении сессии."""
    profile = _profile([_task("abstraction_1", 1), _task("abstraction_1", 1), _task("abstraction_2", 1)])
    assert profile["Абстракция"]["score"] == 2
    assert profile["Абстракция"]["deficit"] == 0.0


# ── Встраивание в результат теста ──────────────────────────────────────────────

def test_profile_is_part_of_the_test_result():
    result = summarize_moca_tasks([_task("delayed_recall", 3), _task("abstraction_1", 1)])
    domains = {item["domain"]: item for item in result["domains"]}
    assert [item["domain"] for item in result["domains"]] == list(COGNITIVE_DOMAINS)
    assert domains["Память"]["score"] == 3
    assert domains["Память"]["deficit"] == pytest.approx(0.4)


def test_domain_scores_sum_to_the_total_score():
    tasks = [
        _task("delayed_recall", 4),
        _task("attention_serial", 2),
        _task("language_fluency", 1),
        _task("abstraction_1", 1),
        _task("memory_1", 0),
    ]
    result = summarize_moca_tasks(tasks)
    assert sum(item["score"] for item in result["domains"]) == result["score"]

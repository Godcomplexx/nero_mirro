"""Подстройка уровня сложности под результаты занятий."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.screening.difficulty_policy import (
    EASY_RATE,
    HARD_RATE,
    MAX_LEVEL,
    MIN_DAYS_AT_LEVEL,
    MIN_LEVEL,
    classify,
    has_levels,
    next_level,
    success_rate,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def days_ago(count: float) -> str:
    return (NOW - timedelta(days=count)).isoformat()


def a_pass(
    *,
    level: int = 1,
    ago: float = 0.0,
    rate: float = 0.9,
    metric: str = "u01_correct_action_rate",
    completion: str = "completed",
    validity: str = "valid",
) -> dict:
    return {
        "difficulty_level": level,
        "presented_at": days_ago(ago),
        "completion_status": completion,
        "technical_validity": validity,
        "metrics": {metric: rate},
    }


# ── Соответствие матрице игр ──────────────────────────────────────────────────

MATRIX_GAMES_WITH_LEVELS = {
    "GM-01", "GM-02", "GM-03", "GM-04", "GM-06",
    "GM-07", "GM-09", "GM-10", "GM-14", "GM-17", "GM-18", "GM-22",
}


def test_levels_follow_the_game_matrix():
    """Уровни заданы матрицей игр; здесь их нельзя назначить самовольно."""
    covered = {game.code for game in GAME_CATALOG if has_levels(game.code)}
    assert covered == MATRIX_GAMES_WITH_LEVELS


def test_a_game_without_levels_always_stays_at_the_first():
    assert next_level("GM-13", [a_pass(rate=1.0, ago=10)], now=NOW) == MIN_LEVEL


# ── Как оценивается прохождение ───────────────────────────────────────────────

def test_an_easy_pass_is_the_one_done_almost_without_errors():
    assert classify("GM-07", a_pass(rate=EASY_RATE)) == "easy"


def test_a_suitable_pass_is_neither_raised_nor_lowered():
    assert classify("GM-07", a_pass(rate=(EASY_RATE + HARD_RATE) / 2)) == "suitable"


def test_a_hard_pass_is_the_one_with_few_correct_actions():
    assert classify("GM-07", a_pass(rate=HARD_RATE - 0.01)) == "hard"


def test_an_unfinished_pass_counts_as_too_hard():
    assert classify("GM-07", a_pass(rate=1.0, completion="incomplete")) == "hard"


def test_a_technically_invalid_pass_is_not_judged_at_all():
    """Сорванная запись говорит об оборудовании, а не о способностях человека."""
    assert classify("GM-07", a_pass(rate=0.1, validity="invalid")) == "unknown"


def test_the_tower_is_measured_by_closeness_to_the_shortest_solution():
    """Готовой доли верных действий у башни нет."""
    perfect = {"e01_valid_move_count": 7, "e05_moves_above_minimum": 0}
    clumsy = {"e01_valid_move_count": 20, "e05_moves_above_minimum": 13}
    assert success_rate("GM-22", perfect) == 1.0
    assert success_rate("GM-22", clumsy) < HARD_RATE


def test_a_missing_metric_leaves_the_level_alone():
    """Неизвестный результат не повод ни повышать, ни понижать."""
    assert classify("GM-07", {"metrics": {}}) == "unknown"


# ── Переход на следующий уровень ──────────────────────────────────────────────

def test_the_course_starts_at_the_first_level():
    assert next_level("GM-07", [], now=NOW) == MIN_LEVEL


def test_the_level_holds_for_the_first_days_even_when_everything_is_easy():
    """Первые дни занятие идёт на первом уровне: так задан курс."""
    recent = [a_pass(ago=0.5, rate=1.0), a_pass(ago=0.1, rate=1.0)]
    assert next_level("GM-07", recent, now=NOW) == MIN_LEVEL


def test_the_level_rises_when_the_game_stays_easy_after_those_days():
    passes = [a_pass(ago=MIN_DAYS_AT_LEVEL + 1, rate=1.0), a_pass(ago=0.1, rate=1.0)]
    assert next_level("GM-07", passes, now=NOW) == MIN_LEVEL + 1


def test_a_single_good_result_does_not_raise_the_level():
    """Разовый успех может объясняться удачным днём."""
    passes = [a_pass(ago=5, rate=0.5), a_pass(ago=0.1, rate=1.0)]
    assert next_level("GM-07", passes, now=NOW) == MIN_LEVEL


def test_the_level_never_goes_above_the_highest_one():
    passes = [a_pass(level=MAX_LEVEL, ago=5, rate=1.0), a_pass(level=MAX_LEVEL, ago=0.1, rate=1.0)]
    assert next_level("GM-07", passes, now=NOW) == MAX_LEVEL


# ── Возврат на предыдущий уровень ─────────────────────────────────────────────

def test_the_level_drops_when_the_game_turns_out_too_hard():
    """Адаптация, умеющая только усложнять, оставит человека на непосильном."""
    passes = [a_pass(level=2, ago=1, rate=0.1), a_pass(level=2, ago=0.1, rate=0.1)]
    assert next_level("GM-07", passes, now=NOW) == 1


def test_lowering_does_not_wait_for_the_holding_period():
    passes = [a_pass(level=2, ago=0.2, rate=0.05), a_pass(level=2, ago=0.1, rate=0.05)]
    assert next_level("GM-07", passes, now=NOW) == 1


def test_the_level_never_drops_below_the_first_one():
    passes = [a_pass(level=1, ago=1, rate=0.0), a_pass(level=1, ago=0.1, rate=0.0)]
    assert next_level("GM-07", passes, now=NOW) == MIN_LEVEL


def test_one_bad_result_does_not_lower_the_level():
    passes = [a_pass(level=2, ago=1, rate=0.9), a_pass(level=2, ago=0.1, rate=0.1)]
    assert next_level("GM-07", passes, now=NOW) == 2


# ── Состав занятия ────────────────────────────────────────────────────────────

def test_every_game_of_a_session_carries_its_level():
    from neuro_mirror.plugins.games.registry import implemented_game_codes
    from neuro_mirror.screening.training_session import build_training_session

    profile = [
        {"domain": "Память", "score": 3, "max_score": 5},
        {"domain": "Внимание", "score": 1, "max_score": 5},
        {"domain": "Речь", "score": 0, "max_score": 3},
        {"domain": "Абстракция", "score": 1, "max_score": 2},
    ]
    session = build_training_session(profile, available_codes=implemented_game_codes())
    assert session["games"]
    assert all(game["difficulty_level"] == MIN_LEVEL for game in session["games"])


def test_a_session_raises_the_level_of_the_games_that_became_easy():
    from neuro_mirror.plugins.games.registry import implemented_game_codes
    from neuro_mirror.screening.training_session import build_training_session

    # У игр показатель успеха разный, поэтому заглушка отдаёт их все: иначе
    # часть игр получила бы «неизвестно» и осталась бы на первом уровне.
    every_metric = {
        "u01_correct_action_rate": 1.0,
        "u08_completion_rate": 1.0,
        "m08_series_accuracy": 1.0,
        "m07_target_recognition_rate": 1.0,
        "a06_tracking_accuracy": 1.0,
        "a07_found_difference_rate": 1.0,
        "u01_first_attempt_word_accuracy": 1.0,
        "e01_valid_move_count": 7,
        "e05_moves_above_minimum": 0,
    }

    def passes(_code: str) -> list[dict]:
        one = {
            "difficulty_level": MIN_LEVEL,
            "presented_at": days_ago(MIN_DAYS_AT_LEVEL + 2),
            "completion_status": "completed",
            "technical_validity": "valid",
            "metrics": every_metric,
        }
        later = dict(one, presented_at=days_ago(0.1))
        return [one, later]

    profile = [
        {"domain": "Память", "score": 3, "max_score": 5},
        {"domain": "Внимание", "score": 1, "max_score": 5},
        {"domain": "Речь", "score": 0, "max_score": 3},
        {"domain": "Абстракция", "score": 1, "max_score": 2},
    ]
    session = build_training_session(
        profile,
        available_codes=implemented_game_codes(),
        passes_for_game=passes,
    )
    for game in session["games"]:
        expected = MIN_LEVEL + 1 if has_levels(game["game_code"]) else MIN_LEVEL
        assert game["difficulty_level"] == expected, game["game_code"]

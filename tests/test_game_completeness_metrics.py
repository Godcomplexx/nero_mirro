"""Признаки завершённости и технической пригодности у всех игр.

Без них отчёт пишет «не определено», а подстройка сложности не меняет уровень
вовсе: непройденное занятие неотличимо от пройденного, а сорванная запись —
от слабого результата.

Ожидаемое число проб каждая игра передаёт сама. Умолчание в таком месте уже
дважды молча расходилось с набором стимулов: в лабиринте и в башне
безошибочное прохождение засчитывалось как незавершённое.
"""
from __future__ import annotations

import inspect

import pytest

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening import (
    gm01_scoring, gm03_scoring, gm04_scoring, gm06_scoring, gm09_scoring,
    gm10_scoring, gm11_scoring, gm13_scoring, gm15_scoring, gm16_scoring,
)


def complete_runs() -> dict[str, dict]:
    """Полностью и чисто пройденное занятие каждой игры."""
    return {
        "GM-01": gm01_scoring.score_gm01([{"correct": True}] * 8, pair_count=8, completed=True),
        "GM-03": gm03_scoring.score_gm03(
            [{"correct": True, "expected": [1, 1], "selected": [1, 1]}] * 3, expected_rooms=3),
        "GM-04": gm04_scoring.score_gm04(
            [{"targets": [1, 2], "selected": [1, 2], "correct": True}] * 3, expected_rounds=3),
        "GM-06": gm06_scoring.score_gm06(
            [{"expected_sequence": [1, 2], "correct_positions": 2, "correct": True}] * 4,
            expected_rounds=4),
        "GM-09": gm09_scoring.score_gm09(
            [{"targets": [1], "selected": [1], "correct": True}] * 5, expected_rounds=5),
        "GM-10": gm10_scoring.score_gm10([{"correct": True, "reaction_ms": 900}] * 4, 4, finished=True),
        "GM-11": gm11_scoring.score_gm11(
            [{"correct": True, "interval_ms": 800, "rule_index": 0, "transcript": "девяносто три"}],
            expected_rules=1),
        "GM-13": gm13_scoring.score_gm13(
            [{"valid_words": ["кот"], "tokens": ["кот"], "duration_ms": 60_000}] * 2,
            expected_categories=2),
        "GM-15": gm15_scoring.score_gm15(
            [{"valid": True, "correct": True, "reaction_ms": 700}] * 5, expected_items=5),
        "GM-16": gm16_scoring.score_gm16(
            [{"valid_words": ["лес"], "tokens": ["лес"], "duration_ms": 60_000}], expected_rounds=1),
    }


@pytest.mark.parametrize("code, metrics", sorted(complete_runs().items()))
def test_a_finished_run_is_marked_complete_and_usable(code, metrics):
    assert metrics["u06_complete"] is True, code
    assert metrics["u06_technically_valid"] is True, code


# ── Незавершённое занятие ─────────────────────────────────────────────────────

def test_a_run_stopped_halfway_is_not_complete():
    metrics = gm03_scoring.score_gm03(
        [{"correct": True, "expected": [1, 1], "selected": [1, 1]}], expected_rooms=3)
    assert metrics["u06_complete"] is False


def test_a_card_board_left_unsolved_is_not_complete():
    metrics = gm01_scoring.score_gm01([{"correct": False}] * 3, pair_count=8, completed=False)
    assert metrics["u06_complete"] is False


# ── Непригодная запись ────────────────────────────────────────────────────────

def test_a_round_without_stimuli_is_not_usable():
    """Пустой раунд означает, что задание не предъявилось."""
    metrics = gm09_scoring.score_gm09([{"targets": [], "selected": []}], expected_rounds=1)
    assert metrics["u06_technically_valid"] is False


def test_speech_that_was_never_recognised_is_not_usable():
    """Молчащий микрофон не говорит ни о словарном запасе, ни о назывании."""
    naming = gm15_scoring.score_gm15([{"valid": False, "correct": False}] * 5, expected_items=5)
    fluency = gm13_scoring.score_gm13(
        [{"valid_words": [], "tokens": [], "invalid_words": [], "duration_ms": 60_000}] * 2,
        expected_categories=2)
    assert naming["u06_technically_valid"] is False
    assert fluency["u06_technically_valid"] is False


def test_an_empty_run_is_neither_complete_nor_usable():
    metrics = gm04_scoring.score_gm04([], expected_rounds=3)
    assert metrics["u06_complete"] is False
    assert metrics["u06_technically_valid"] is False


# ── Охват библиотеки ──────────────────────────────────────────────────────────

SCORERS = {
    "GM-01": gm01_scoring.score_gm01, "GM-03": gm03_scoring.score_gm03,
    "GM-04": gm04_scoring.score_gm04, "GM-06": gm06_scoring.score_gm06,
    "GM-09": gm09_scoring.score_gm09, "GM-10": gm10_scoring.score_gm10,
    "GM-11": gm11_scoring.score_gm11, "GM-13": gm13_scoring.score_gm13,
    "GM-15": gm15_scoring.score_gm15, "GM-16": gm16_scoring.score_gm16,
}


@pytest.mark.parametrize("code, scorer", sorted(SCORERS.items()))
def test_the_expected_count_is_asked_for_and_not_assumed(code, scorer):
    """Умолчание в этом месте дважды разошлось с набором стимулов."""
    required = [
        name for name, param in inspect.signature(scorer).parameters.items()
        if param.kind is inspect.Parameter.KEYWORD_ONLY and param.default is inspect.Parameter.empty
    ]
    assert required, f"{code}: ожидаемое число проб задано умолчанием"


def test_every_implemented_game_reports_whether_it_was_finished():
    """Иначе половина библиотеки не участвует в подстройке сложности."""
    import importlib

    missing = []
    for game in GAME_CATALOG:
        if game.code not in implemented_game_codes():
            continue
        number = game.code.split("-")[1]
        try:
            module = importlib.import_module(f"neuro_mirror.screening.gm{number}_scoring")
        except ModuleNotFoundError:
            missing.append(game.code)
            continue
        source = inspect.getsource(module)
        if "u06_complete" not in source:
            missing.append(game.code)
    assert not missing, f"не сообщают о завершении: {missing}"

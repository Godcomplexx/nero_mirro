"""Переход уровня формы по «Методике подбора и оценки тренировочного курса» v2."""
from __future__ import annotations

import pytest

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.screening import gm02_scoring, gm18_scoring, gm22_scoring
from neuro_mirror.screening.difficulty_policy import (
    FLAG_CEILING,
    FLAG_HARD,
    MAX_LEVEL,
    MIN_LEVEL,
    FormState,
    Success,
    apply_pass,
    assign_level,
    counted_success,
    has_levels,
    success,
)

# ── Соответствие матрице игр ──────────────────────────────────────────────────

# Формы, у которых курс меняет уровень: 12 форм с уровнями из «Матрицы игр
# v5» и показателем успешности по методике (раздел 7, «Готовность к
# адаптации»: да), плюс GM-05 по решению команды. У остальных уровни
# предварительные (draft в game_levels.json): игра идёт на них, а курс
# уровень не меняет.
ADAPTIVE_FORMS = {
    "GM-01", "GM-02", "GM-03", "GM-04", "GM-05", "GM-06",
    "GM-07", "GM-09", "GM-10", "GM-14", "GM-17", "GM-18", "GM-22",
}

# Адаптивные формы с предварительными уровнями — только явно перечисленные.
ADAPTIVE_ON_DRAFT_LEVELS = {"GM-05"}


def test_only_forms_ready_for_adaptation_change_level():
    """Курс меняет уровень только у форм, готовых к адаптации по методике."""
    covered = {game.code for game in GAME_CATALOG if has_levels(game.code)}
    assert covered == ADAPTIVE_FORMS


def test_every_form_has_three_levels_in_the_catalog():
    for game in GAME_CATALOG:
        assert len(game.difficulty_levels) == 3, game.code


# ── Успешность: числитель и знаменатель ───────────────────────────────────────

def test_the_threshold_is_checked_exactly():
    """85 из 100 — ровно порог, 84 из 100 — ниже."""
    assert Success(85, 100).at_least(85)
    assert not Success(84, 100).at_least(85)
    assert Success(17, 20).at_least(85)
    assert Success(1, 2).at_least(50)
    assert not Success(49, 100).at_least(50)


def test_a_form_without_levels_has_no_success():
    assert success("GM-05", {"m07_target_recognition_rate": 1.0}) is None


def test_success_is_taken_from_counts_not_from_a_share():
    """Доля без числителя и знаменателя не годится для точной проверки."""
    assert success("GM-03", {"u01_correct_action_rate": 0.9}) is None
    assert success("GM-03", {"u01_correct_actions": 9, "u01_actions_total": 10}) == Success(9, 10)


def test_broken_counts_are_not_a_success():
    assert success("GM-03", {"u01_correct_actions": 11, "u01_actions_total": 10}) is None
    assert success("GM-03", {"u01_correct_actions": 0, "u01_actions_total": 0}) is None


def test_puzzle_counts_pieces_placed_on_the_first_move():
    """GM-18: U01 — фрагменты, установленные верно с первой попытки."""
    metrics = gm18_scoring.score_gm18(
        [{"moves": 5, "minimum_moves": 4, "first_attempt_pieces": 4, "moved_pieces": 6}],
        30_000,
        required_puzzles=1,
    )
    assert success("GM-18", metrics) == Success(4, 6)
    assert metrics["u06_complete"] is True
    assert metrics["u06_technically_valid"] is True


def test_tower_counts_towers_built_into_the_target():
    """GM-22: U03 — доля башен, собранных в целевую конфигурацию."""
    events = [{"legal_move": True, "level_complete": True, "minimum_moves": 7}]
    metrics = gm22_scoring.score_gm22(events, 40_000, required_levels=1)
    assert success("GM-22", metrics) == Success(1, 1)


def test_sequence_counts_every_series_not_only_the_last():
    """GM-02: девять верных серий из десяти — не ноль из-за последней ошибки."""
    rounds = [{"correct": True}] * 9 + [{"correct": False}]
    metrics = gm02_scoring.score_gm02_series(rounds)
    assert success("GM-02", metrics) == Success(9, 10)


# ── Какое прохождение учитывается ─────────────────────────────────────────────

def outcome(correct: int, total: int, *, completion="completed", validity="valid") -> dict:
    return {
        "completion_status": completion,
        "technical_validity": validity,
        "metrics": {"u01_correct_actions": correct, "u01_actions_total": total},
    }


def test_a_finished_pass_is_counted():
    assert counted_success("GM-17", outcome(9, 10)) == Success(9, 10)


def test_a_pass_ended_by_time_or_attempts_is_counted():
    assert counted_success("GM-17", outcome(3, 10, completion="incomplete")) == Success(3, 10)


def test_a_technically_invalid_pass_is_not_counted():
    assert counted_success("GM-17", outcome(9, 10, validity="invalid")) is None


def test_a_pass_without_completeness_indicators_is_not_counted():
    assert counted_success("GM-17", outcome(9, 10, completion="unknown")) is None
    assert counted_success("GM-17", outcome(9, 10, validity="unknown")) is None


# ── Правило перехода ──────────────────────────────────────────────────────────

def test_one_pass_at_85_percent_raises_the_level():
    assert apply_pass(FormState(level=1), Success(17, 20)).level == 2


def test_a_pass_in_the_target_corridor_keeps_the_level():
    state = apply_pass(FormState(level=2), Success(7, 10))
    assert state.level == 2
    assert state.below_half_streak == 0


def test_one_pass_below_half_does_not_lower_the_level():
    state = apply_pass(FormState(level=2), Success(2, 10))
    assert state.level == 2
    assert state.below_half_streak == 1


def test_two_passes_below_half_in_a_row_lower_the_level():
    state = apply_pass(FormState(level=2), Success(2, 10))
    state = apply_pass(state, Success(4, 10))
    assert state.level == 1
    assert state.below_half_streak == 0, "счётчик сбрасывается при смене уровня"


def test_a_pass_in_between_breaks_the_series():
    state = apply_pass(FormState(level=2), Success(2, 10))
    state = apply_pass(state, Success(6, 10))
    state = apply_pass(state, Success(2, 10))
    assert state.level == 2


def test_two_failures_at_the_first_level_mark_the_form_hard():
    state = apply_pass(FormState(level=MIN_LEVEL), Success(1, 10))
    state = apply_pass(state, Success(1, 10))
    assert state.level == MIN_LEVEL
    assert FLAG_HARD in state.flags


def test_success_at_the_top_level_marks_the_ceiling():
    state = apply_pass(FormState(level=MAX_LEVEL), Success(10, 10))
    assert state.level == MAX_LEVEL
    assert FLAG_CEILING in state.flags


def test_the_level_changes_by_at_most_one_step():
    assert apply_pass(FormState(level=1), Success(10, 10)).level == 2


@pytest.mark.parametrize("level", [1, 2, 3])
def test_the_level_stays_within_the_matrix(level):
    for result in (Success(10, 10), Success(0, 10)):
        state = FormState(level=level)
        for _ in range(4):
            state = apply_pass(state, result)
            assert MIN_LEVEL <= state.level <= MAX_LEVEL


# ── Присвоение уровня перед 6-м занятием ──────────────────────────────────────

def test_a_steady_form_gets_the_second_level():
    assert assign_level([Success(9, 10), Success(9, 10), Success(8, 10)]).level == 2


def test_a_form_that_dropped_at_the_end_stays_at_the_first_level():
    """Последнее прохождение ниже 0,70: результат к концу освоения падает."""
    results = [Success(10, 10), Success(10, 10), Success(6, 10)]
    total = Success(26, 30)
    assert total.at_least(85)
    assert assign_level(results).level == 1


def test_the_summary_is_correct_over_all_rather_than_an_average_of_shares():
    """Сводная успешность — сумма верных на сумму всех."""
    # Средняя доля (1,0 + 0,7) / 2 = 0,85, а сводная 8/11 ≈ 0,73.
    assert assign_level([Success(1, 1), Success(7, 10)]).level == 1


def test_a_form_failing_through_mastering_is_marked_hard():
    state = assign_level([Success(2, 10), Success(3, 10), Success(4, 10)])
    assert state.level == 1
    assert FLAG_HARD in state.flags


def test_a_form_not_shown_in_mastering_starts_at_the_first_level():
    assert assign_level([]) == FormState()


# ── Утверждённые и предварительные уровни ─────────────────────────────────────

def test_every_game_says_where_its_levels_come_from():
    from neuro_mirror.plugins.games.difficulty_config import level_config

    for game in GAME_CATALOG:
        assert level_config(game.code)["source"].strip(), game.code


def test_levels_missing_in_the_matrix_are_marked_draft():
    """В матрице у этих форм уровни пустые — значения предварительные."""
    from neuro_mirror.plugins.games.difficulty_config import level_status

    draft = {game.code for game in GAME_CATALOG if level_status(game.code) == "draft"}
    assert draft == {
        "GM-05", "GM-08", "GM-11", "GM-12", "GM-13", "GM-15",
        "GM-16", "GM-19", "GM-20", "GM-21", "GM-23", "GM-24",
    }


def test_the_course_adapts_only_forms_with_approved_levels():
    """Исключение — только явно перечисленные формы, с пометкой в JSON."""
    from neuro_mirror.plugins.games.difficulty_config import level_config, level_status

    for code in ADAPTIVE_FORMS - ADAPTIVE_ON_DRAFT_LEVELS:
        assert level_status(code) == "configured", code
    for code in ADAPTIVE_ON_DRAFT_LEVELS:
        assert level_status(code) == "draft", code
        assert "согласовать" in level_config(code).get("note", ""), code


def test_the_levels_document_matches_the_json():
    """docs/game-levels.md собирается из game_levels.json и не отстаёт от него."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("make_doc", root / "docs" / "make_game_levels_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    current = module.TARGET.read_text(encoding="utf-8")
    module.main()
    assert module.TARGET.read_text(encoding="utf-8") == current, "запустите python docs/make_game_levels_doc.py"


# ── GM-05: верные решения по каждому слову списка ─────────────────────────────

def word_list_pass(selected_old: int, selected_new: int, *, old: int = 4, new: int = 4) -> dict:
    from neuro_mirror.screening.gm05_scoring import score_gm05_rounds

    targets = [f"старое{i}" for i in range(old)]
    distractors = [f"новое{i}" for i in range(new)]
    selected = targets[:selected_old] + distractors[:selected_new]
    return score_gm05_rounds(
        [{"targets": targets, "distractors": distractors, "selected": selected}], expected_rounds=1
    )


@pytest.mark.parametrize("selected_old, selected_new, expected, action", [
    (4, 0, Success(8, 8), "up"),
    (3, 1, Success(6, 8), "keep"),
    (4, 4, Success(4, 8), "keep"),
    (0, 0, Success(4, 8), "keep"),
])
def test_word_list_counts_every_decision(selected_old, selected_new, expected, action):
    """Отметка всех слов подряд или ни одного — около половины, не повышение."""
    result = success("GM-05", word_list_pass(selected_old, selected_new))
    assert result == expected
    level = apply_pass(FormState(level=1), result).level
    assert level == (2 if action == "up" else 1)


def test_word_list_keeps_hits_and_false_alarms_for_the_report():
    metrics = word_list_pass(3, 1)
    assert metrics["m07_recognized_words"] == 3
    assert metrics["m07_words_total"] == 4
    assert metrics["g08_false_alarms"] == 1
    assert metrics["g08_new_words_total"] == 4

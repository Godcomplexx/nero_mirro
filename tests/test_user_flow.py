"""Полный путь человека: опросник, скрининг, занятия, подстройка сложности.

Проверяется не отдельная часть, а их стык: по отдельности расчёт баллов,
подбор игр и правило уровней уже покрыты, а здесь важно, что они соединяются
в один путь и что состав занятий со временем меняется.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening.difficulty_policy import MIN_DAYS_AT_LEVEL, MIN_LEVEL, has_levels
from neuro_mirror.screening.moca_scoring import VOICE_MOCA_MAX_SCORE, score_moca_tasks
from neuro_mirror.screening.san_survey import (
    MOMENT_AFTER,
    MOMENT_BEFORE,
    QUESTION_IDS,
    compare,
    questionnaire,
    score_san,
)
from neuro_mirror.screening.training_plan import plan_session
from neuro_mirror.screening.training_session import build_training_session

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

# Ответы человека на задания скрининга: часть верно, часть нет.
MOCA_ANSWERS = [
    {"task_id": "delayed_recall", "transcript": "лицо бархат церковь"},
    {"task_id": "attention_digits_forward", "transcript": "2 1 8 5 4"},
    {"task_id": "attention_digits_backward", "transcript": "7 4 2"},
    {"task_id": "attention_serial", "transcript": "девяносто три"},
    {"task_id": "language_sentence_1", "transcript": "я знаю только одно"},
    {"task_id": "language_sentence_2",
     "transcript": "кошка всегда пряталась под диваном когда собаки были в комнате"},
    {"task_id": "language_fluency",
     "transcript": "лодка лампа лес лиса лето луна лужа лимон лыжи лось лента"},
    {"task_id": "abstraction_1", "transcript": "это транспорт"},
    {"task_id": "abstraction_2", "transcript": "это измерительные приборы"},
]


def session_for(passes=None):
    result = score_moca_tasks(MOCA_ANSWERS)
    return result, build_training_session(
        result["domains"],
        available_codes=implemented_game_codes(),
        passes_for_game=passes,
    )


def a_pass(level: int, ago: float, rate: float) -> dict:
    """Одно прохождение игры с указанным исходом."""
    return {
        "difficulty_level": level,
        "presented_at": (NOW - timedelta(days=ago)).isoformat(),
        "completion_status": "completed",
        "technical_validity": "valid",
        "metrics": {
            "u01_correct_action_rate": rate,
            "u08_completion_rate": rate,
            "m08_series_accuracy": rate,
            "m07_target_recognition_rate": rate,
            "a06_tracking_accuracy": rate,
            "a07_found_difference_rate": rate,
            "u01_first_attempt_word_accuracy": rate,
            "e01_valid_move_count": 10,
            "e05_moves_above_minimum": round(10 * (1 - rate)),
        },
    }


# ── Опросник до занятия ───────────────────────────────────────────────────────

def test_the_survey_asks_six_questions_in_three_blocks():
    """Шесть вопросов тремя блоками — состав задан методикой."""
    form = questionnaire()
    assert len(form["questions"]) == 6
    assert len(form["scale"]) == 5
    groups = {item["group"] for item in form["questions"]}
    assert groups == {"Самочувствие", "Активность", "Настроение"}
    for question in form["questions"]:
        assert len(question["options"]) == 5
        assert all(option["label"].strip() for option in question["options"])


def test_the_survey_shows_how_the_session_changed_the_state():
    """Опросник предъявляется до и после: смысл в сравнении, а не в баллах."""
    before = score_san({key: 2 for key in QUESTION_IDS})
    after = score_san({key: 4 for key in QUESTION_IDS})
    assert before["complete"] and after["complete"]
    changes = compare(before, after)["groups"]
    assert all(row["change"] == 2.0 for row in changes)


def test_an_unanswered_question_is_not_replaced_by_an_average():
    """Подставленное значение не отличить от настоящего ответа."""
    partial = score_san({key: 3 for key in QUESTION_IDS[:4]})
    assert partial["complete"] is False
    assert partial["answered"] == 4


# ── Скрининг ──────────────────────────────────────────────────────────────────

def test_the_screening_gives_a_profile_over_four_domains():
    result, _ = session_for()
    assert 0 <= result["score"] <= VOICE_MOCA_MAX_SCORE
    domains = {item["domain"]: item for item in result["domains"]}
    assert set(domains) == {"Память", "Внимание", "Речь", "Абстракция"}
    assert sum(item["max_score"] for item in result["domains"]) == VOICE_MOCA_MAX_SCORE
    for item in result["domains"]:
        assert 0 <= item["score"] <= item["max_score"]
        assert 0.0 <= item["deficit"] <= 1.0


# ── Занятие ───────────────────────────────────────────────────────────────────

def test_the_session_is_built_from_the_screening_result():
    result, session = session_for()
    assert session["session_size"] == sum(session["plan"].values())
    assert session["plan"] == plan_session(result["domains"])
    assert [game["position"] for game in session["games"]] == list(
        range(1, session["session_size"] + 1)
    )


def test_a_weaker_domain_gets_more_tasks_than_a_stronger_one():
    """Состав занятия идёт от недобора, иначе подбор не нужен вовсе."""
    weak = [
        {"domain": "Память", "score": 0, "max_score": 5},
        {"domain": "Внимание", "score": 5, "max_score": 5},
        {"domain": "Речь", "score": 3, "max_score": 3},
        {"domain": "Абстракция", "score": 2, "max_score": 2},
    ]
    plan = plan_session(weak)
    assert plan["Память"] > plan["Внимание"]
    assert all(count >= 1 for count in plan.values()), "домен не должен выпадать"


def test_the_session_is_not_one_pool_repeated():
    """Игры в занятии разные, иначе это не подбор, а один и тот же набор."""
    _, session = session_for()
    codes = [game["game_code"] for game in session["games"]]
    assert len(codes) == len(set(codes))


def test_domains_do_not_come_in_blocks():
    """Четыре задания одного домена подряд утомляют."""
    _, session = session_for()
    domains = [game["domain"] for game in session["games"]]
    assert all(domains[i] != domains[i + 1] for i in range(len(domains) - 1))


# ── Подстройка сложности ──────────────────────────────────────────────────────

def test_the_course_starts_at_the_first_level():
    _, session = session_for()
    assert all(game["difficulty_level"] == MIN_LEVEL for game in session["games"])


def test_the_level_holds_through_the_first_days():
    """Первые дни занятие идёт на первом уровне, даже когда всё даётся легко."""
    easy_today = lambda _code: [a_pass(1, 0.5, 1.0), a_pass(1, 0.1, 1.0)]
    _, session = session_for(easy_today)
    assert all(game["difficulty_level"] == MIN_LEVEL for game in session["games"])


def test_a_game_that_stays_easy_is_offered_harder_later():
    easy_before = lambda _code: [
        a_pass(1, MIN_DAYS_AT_LEVEL + 2, 1.0), a_pass(1, 0.1, 1.0)
    ]
    _, session = session_for(easy_before)
    for game in session["games"]:
        expected = MIN_LEVEL + 1 if has_levels(game["game_code"]) else MIN_LEVEL
        assert game["difficulty_level"] == expected, game["game_code"]


def test_a_game_that_turns_out_too_hard_is_offered_easier():
    struggling = lambda _code: [a_pass(2, 1, 0.1), a_pass(2, 0.1, 0.1)]
    _, session = session_for(struggling)
    levelled = [g for g in session["games"] if has_levels(g["game_code"])]
    assert levelled, "в занятии нет ни одной игры с уровнями"
    assert all(game["difficulty_level"] == MIN_LEVEL for game in levelled)


def test_every_task_carries_what_is_needed_to_run_it():
    """Интерфейс проигрывает выданный список и ничего не досчитывает."""
    _, session = session_for()
    for game in session["games"]:
        assert game["game_code"] and game["title"]
        assert game["stimulus_set"]
        assert game["domain"] and game["domain_code"]
        assert MIN_LEVEL <= game["difficulty_level"] <= 3


# ── Путь целиком ──────────────────────────────────────────────────────────────

def test_the_whole_path_holds_together():
    """Опросник до, скрининг, занятие, опросник после — один путь."""
    before = score_san({key: 3 for key in QUESTION_IDS})
    assert before["complete"]

    result, session = session_for()
    assert result["score"] >= 0
    assert session["session_size"] == 10
    assert not session["skipped"], session["skipped"]

    # Домены занятия берутся из профиля скрининга, а не откуда-то ещё.
    profile_domains = {item["domain"] for item in result["domains"]}
    assert {game["domain"] for game in session["games"]} <= profile_domains

    after = score_san({key: 4 for key in QUESTION_IDS})
    changes = compare(before, after)["groups"]
    assert len(changes) == 3
    assert all(row["change"] is not None for row in changes)


def test_the_moment_of_the_survey_is_recorded():
    """Без отметки «до» или «после» сравнивать нечего."""
    assert MOMENT_BEFORE != MOMENT_AFTER

"""Полный путь человека: опросник, скрининг, занятия, подстройка сложности.

Проверяется не отдельная часть, а их стык: по отдельности расчёт баллов,
подбор игр и правило уровней уже покрыты, а здесь важно, что они соединяются
в один путь и что состав занятий со временем меняется.
"""
from __future__ import annotations

from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening.difficulty_policy import MIN_LEVEL, Success, has_levels
from neuro_mirror.screening.moca_scoring import VOICE_MOCA_MAX_SCORE, score_moca_tasks
from neuro_mirror.screening.san_survey import (
    MOMENT_AFTER,
    MOMENT_BEFORE,
    QUESTION_IDS,
    compare,
    questionnaire,
    score_san,
)
from neuro_mirror.screening.training_course import CoursePass, apply_levels, course_slots, form_states
from neuro_mirror.screening.training_plan import plan_session
from neuro_mirror.screening.training_session import build_training_session

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


def session_for(session_number: int = 1, passes: list[CoursePass] = ()):
    """Занятие курса с данным номером после указанных прохождений.

    Состав курса один на все 12 занятий; уровни ставятся при открытии
    занятия по прохождениям до него.
    """
    result = score_moca_tasks(MOCA_ANSWERS)
    composition = build_training_session(result["domains"], available_codes=implemented_game_codes())
    slot = course_slots(composition["games"], "u1")[session_number - 1]
    states, _ = form_states(passes, session_number)
    apply_levels(slot["games"], states)
    return result, {**composition, "games": slot["games"]}


ADAPTIVE_CODES = sorted(code for code in implemented_game_codes() if has_levels(code))


def every_form(sessions, result: Success) -> list[CoursePass]:
    """Каждая адаптивная форма пройдена в каждом из занятий с одним исходом."""
    return [CoursePass(number, code, result) for number in sessions for code in ADAPTIVE_CODES]


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

def levels(session: dict) -> list[int]:
    return [game["difficulty_level"] for game in session["games"] if game["adaptation"] == "adaptive"]


def test_the_course_starts_at_the_first_level():
    _, session = session_for()
    assert levels(session)
    assert set(levels(session)) == {MIN_LEVEL}


def test_the_level_holds_through_the_first_five_sessions():
    """Калибровка и освоение идут на первом уровне, даже когда всё легко."""
    _, session = session_for(5, every_form(range(1, 5), Success(10, 10)))
    assert set(levels(session)) == {MIN_LEVEL}


def test_a_form_mastered_in_sessions_three_to_five_goes_up_in_the_sixth():
    _, session = session_for(6, every_form(range(3, 6), Success(10, 10)))
    assert set(levels(session)) == {MIN_LEVEL + 1}


def test_a_form_that_turns_out_too_hard_is_offered_easier():
    passes = every_form(range(3, 6), Success(10, 10)) + every_form((6, 7), Success(1, 10))
    _, session = session_for(8, passes)
    assert set(levels(session)) == {MIN_LEVEL}


def test_every_task_carries_what_is_needed_to_run_it():
    """Интерфейс проигрывает выданный список и ничего не досчитывает."""
    _, session = session_for()
    for game in session["games"]:
        assert game["game_code"] and game["title"]
        assert game["stimulus_set"]
        assert game["domain"] and game["domain_code"]
        if game["adaptation"] == "adaptive":
            assert MIN_LEVEL <= game["difficulty_level"] <= 3
        else:
            assert game["difficulty_level"] is None


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

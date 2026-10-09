"""Курс тренировок: 12 занятий, этапы, наборы, уровни форм по занятиям.

По «Методике подбора и оценки тренировочного курса» v2, разделы 4.3–6.5.
"""
from __future__ import annotations

import pytest

from neuro_mirror.plugins.games.catalog import get_game_definition
from neuro_mirror.plugins.games.course_store import (
    ITEM_ABANDONED,
    ITEM_DONE,
    ITEM_NOT_PRESENTED,
    SESSION_COMPLETED,
    SESSION_INCOMPLETE,
    CourseError,
    TrainingCourseStore,
)
from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening.difficulty_policy import FLAG_HARD, FormState, Success
from neuro_mirror.screening.training_course import (
    COURSE_SESSIONS,
    CoursePass,
    form_states,
    randomization_seed,
    stage_for,
    stimulus_set_for,
    stimulus_set_number,
)
from neuro_mirror.screening.training_session import build_training_session

PROFILE = [
    {"domain": "Память", "score": 3, "max_score": 5},
    {"domain": "Внимание", "score": 4, "max_score": 5},
    {"domain": "Речь", "score": 2, "max_score": 3},
    {"domain": "Абстракция", "score": 1, "max_score": 2},
]

GOOD = Success(9, 10)
OK = Success(7, 10)
BAD = Success(2, 10)


# ── Этапы и стимульные наборы ─────────────────────────────────────────────────

def test_the_course_has_twelve_sessions_in_four_stages():
    stages = [stage_for(number).id for number in range(1, COURSE_SESSIONS + 1)]
    assert stages == (
        ["calibration"] * 2 + ["mastering"] * 3 + ["assignment"] + ["adaptive"] * 6
    )


def test_there_is_no_thirteenth_session():
    with pytest.raises(ValueError):
        stage_for(COURSE_SESSIONS + 1)


def test_stimulus_sets_follow_the_stages():
    """1–2 набор 1, 3–5 набор 2, 6 набор 3, 7–11 по очереди 1 и 2, 12 набор 3."""
    numbers = [stimulus_set_number(n) for n in range(1, COURSE_SESSIONS + 1)]
    assert numbers == [1, 1, 2, 2, 2, 3, 1, 2, 1, 2, 1, 3]


def test_set_three_is_not_shown_before_the_sixth_session():
    assert all(stimulus_set_number(n) != 3 for n in range(1, 6))


def test_the_set_name_comes_from_the_matrix():
    cards = get_game_definition("GM-01")
    assert stimulus_set_for(cards, 1) == (cards.stimulus_sets[0], 1)
    assert stimulus_set_for(cards, 6) == (cards.stimulus_sets[2], 3)


def test_a_form_with_one_set_always_shows_it():
    tower = get_game_definition("GM-22")
    assert {stimulus_set_for(tower, n)[0] for n in range(1, 13)} == {tower.stimulus_sets[0]}


def test_the_seed_is_user_form_and_session():
    seed = randomization_seed("u1", "GM-22", 6)
    assert seed == randomization_seed("u1", "GM-22", 6)
    assert seed != randomization_seed("u1", "GM-22", 12)
    assert seed != randomization_seed("u2", "GM-22", 6)


# ── Уровни форм по занятиям ───────────────────────────────────────────────────

def passes(*rows: tuple[int, str, Success | None]) -> list[CoursePass]:
    return [CoursePass(number, code, result) for number, code, result in rows]


@pytest.mark.parametrize("session_number", [1, 2, 3, 4, 5])
def test_levels_do_not_change_in_the_first_five_sessions(session_number):
    history = passes(*[(n, "GM-17", Success(10, 10)) for n in range(1, session_number)])
    states, log = form_states(history, session_number)
    assert states.get("GM-17", FormState()).level == 1
    assert log == []


def test_the_sixth_session_assigns_the_level_from_sessions_three_to_five():
    history = passes((3, "GM-17", GOOD), (4, "GM-17", GOOD), (5, "GM-17", GOOD))
    states, log = form_states(history, 6)
    assert states["GM-17"].level == 2
    assert log[0]["kind"] == "assignment"
    assert log[0]["success"] == {"correct": 27, "total": 30}


def test_calibration_does_not_count_for_the_assignment():
    """Отличная калибровка и слабое освоение — уровень 1."""
    history = passes(
        (1, "GM-17", Success(10, 10)), (2, "GM-17", Success(10, 10)),
        (3, "GM-17", OK), (4, "GM-17", OK), (5, "GM-17", OK),
    )
    states, _ = form_states(history, 6)
    assert states["GM-17"].level == 1


def test_the_sixth_session_never_starts_above_the_second_level():
    history = passes(*[(n, "GM-17", Success(10, 10)) for n in range(1, 6)])
    states, _ = form_states(history, 6)
    assert states["GM-17"].level == 2


def test_from_the_seventh_session_the_level_follows_the_previous_session():
    history = passes(
        (3, "GM-17", GOOD), (4, "GM-17", GOOD), (5, "GM-17", GOOD),
        (6, "GM-17", GOOD),
    )
    states, log = form_states(history, 7)
    assert states["GM-17"].level == 3
    assert log[-1] == {
        "before_session": 7,
        "game_code": "GM-17",
        "kind": "transition",
        "from_level": 2,
        "to_level": 3,
        "flags": [],
        "success": {"correct": 9, "total": 10},
    }


def test_a_form_absent_from_the_previous_session_keeps_its_level():
    history = passes((3, "GM-17", GOOD), (4, "GM-17", GOOD), (5, "GM-17", GOOD))
    states, _ = form_states(history, 9)
    assert states["GM-17"].level == 2


def test_an_uncounted_pass_neither_breaks_nor_joins_the_series():
    history = passes(
        (3, "GM-17", GOOD), (4, "GM-17", GOOD), (5, "GM-17", GOOD),
        (6, "GM-17", BAD), (7, "GM-17", None), (8, "GM-17", BAD),
    )
    states, _ = form_states(history, 9)
    assert states["GM-17"].level == 1


def test_the_level_of_one_form_does_not_move_another():
    history = passes(
        (3, "GM-17", GOOD), (4, "GM-17", GOOD), (5, "GM-17", GOOD),
        (3, "GM-18", OK), (4, "GM-18", OK), (5, "GM-18", OK),
    )
    states, _ = form_states(history, 6)
    assert states["GM-17"].level == 2
    assert states["GM-18"].level == 1


def test_a_form_failing_through_mastering_is_marked_hard_for_the_specialist():
    history = passes((3, "GM-17", BAD), (4, "GM-17", BAD), (5, "GM-17", BAD))
    states, log = form_states(history, 6)
    assert FLAG_HARD in states["GM-17"].flags
    assert log[0]["flags"] == [FLAG_HARD]


def test_forms_without_levels_are_not_adapted():
    history = passes((3, "GM-05", Success(10, 10)))
    states, _ = form_states(history, 6)
    assert "GM-05" not in states


# ── Сборка занятия курса ──────────────────────────────────────────────────────

def session(number: int = 1, **kwargs) -> dict:
    return build_training_session(
        PROFILE,
        session_number=number,
        user_id="u1",
        available_codes=implemented_game_codes(),
        **kwargs,
    )


def test_the_first_session_starts_with_a_simple_click_task():
    """Голос, перетаскивание и ведение курсора первыми не ставятся (5.2)."""
    first = get_game_definition(session(1)["games"][0]["game_code"])
    assert first.response_type.value == "click"
    assert [m.value for m in first.modalities] == ["visual"]


def test_calibration_shows_set_one_and_the_first_level():
    for game in session(1)["games"]:
        assert game["stimulus_set_number"] == 1
        assert game["difficulty_level"] in (1, None)


def test_a_form_without_levels_has_no_level_and_is_marked():
    games = session(1)["games"]
    for game in games:
        if game["adaptation"] == "fixed_config":
            assert game["difficulty_level"] is None
        else:
            assert game["difficulty_level"] == 1


def test_the_session_uses_the_levels_of_the_course():
    states = {code: FormState(level=2) for code in implemented_game_codes()}
    games = session(7, states=states)["games"]
    adaptive = [game for game in games if game["adaptation"] == "adaptive"]
    assert adaptive
    assert all(game["difficulty_level"] == 2 for game in adaptive)


def test_forms_with_levels_go_first_within_a_domain():
    """Формы без уровней берутся, только когда домену не хватает адаптивных."""
    memory = [game for game in session(1)["games"] if game["domain"] == "Память"]
    assert all(game["adaptation"] == "adaptive" for game in memory)


def test_the_second_session_prefers_forms_not_shown_in_the_first():
    first = session(1)
    first_codes = tuple(game["game_code"] for game in first["games"])
    second = session(2, course_sessions=(first_codes,), domain_totals=first["plan"])
    fresh = [game for game in second["games"] if game["game_code"] not in first_codes]
    assert len(fresh) >= 4


def test_with_no_shortfall_the_extra_tasks_rotate_between_domains():
    """Без недобора тройки не достаются всегда памяти и вниманию (4.2)."""
    full = [dict(item, score=item["max_score"]) for item in PROFILE]
    first = build_training_session(full, session_number=1, available_codes=implemented_game_codes())
    second = build_training_session(
        full, session_number=2, available_codes=implemented_game_codes(),
        domain_totals=first["plan"],
    )
    assert first["plan"] != second["plan"]


# ── Хранение курса ────────────────────────────────────────────────────────────

def stored_session(store: TrainingCourseStore, number: int = 1) -> tuple[dict, dict]:
    course = store.latest_course("u1") or store.create_course(
        user_id="u1", entry_session_id="moca-1", profile=PROFILE
    )
    planned = {"number": number, "stage": stage_for(number).id, **session(number), "level_changes": []}
    return course, store.add_session(course, planned)


def finish_item(store: TrainingCourseStore, record: dict, position: int, result: Success | None) -> None:
    item = record["games"][position - 1]
    store.begin_item(user_id="u1", session_number=record["number"], position=position, game_code=item["game_code"])
    store.attach_game_session(
        user_id="u1", session_number=record["number"], position=position, game_session_id=f"g{position}"
    )
    store.record_outcome(
        game_session_id=f"g{position}",
        completion_status="completed",
        technical_validity="valid",
        success=result,
        counted=result is not None,
        metrics={},
    )


def test_the_session_plan_survives_a_restart(tmp_path):
    path = tmp_path / "courses.json"
    store = TrainingCourseStore(path)
    _, record = stored_session(store)
    reopened = TrainingCourseStore(path)
    assert reopened.open_session("u1")["games"] == record["games"]


def test_a_task_left_for_another_is_abandoned(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    _, record = stored_session(store)
    first, second = record["games"][:2]
    store.begin_item(user_id="u1", session_number=1, position=1, game_code=first["game_code"])
    store.begin_item(user_id="u1", session_number=1, position=2, game_code=second["game_code"])
    assert record["games"][0]["status"] == ITEM_ABANDONED


def test_restarting_the_same_task_is_not_abandoning_it(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    _, record = stored_session(store)
    code = record["games"][0]["game_code"]
    store.begin_item(user_id="u1", session_number=1, position=1, game_code=code)
    item = store.begin_item(user_id="u1", session_number=1, position=1, game_code=code)
    assert item["status"] == "started"
    assert item["attempts"] == 2


def test_a_task_cannot_be_started_as_another_form(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    _, record = stored_session(store)
    wrong = record["games"][1]["game_code"]
    with pytest.raises(CourseError):
        store.begin_item(user_id="u1", session_number=1, position=1, game_code=wrong)


def test_ending_early_keeps_the_done_tasks_and_abandons_the_current(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    _, record = stored_session(store)
    finish_item(store, record, 1, GOOD)
    store.begin_item(user_id="u1", session_number=1, position=2, game_code=record["games"][1]["game_code"])
    closed = store.finish_session("u1", reason="пользователь завершил занятие")
    statuses = [item["status"] for item in closed["games"]]
    assert statuses[0] == ITEM_DONE
    assert statuses[1] == ITEM_ABANDONED
    assert set(statuses[2:]) == {ITEM_NOT_PRESENTED}
    assert closed["status"] == SESSION_INCOMPLETE


def test_the_session_closes_itself_after_the_last_task(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    _, record = stored_session(store)
    for position in range(1, len(record["games"]) + 1):
        finish_item(store, record, position, GOOD)
    assert record["status"] == SESSION_COMPLETED
    assert store.open_session("u1") is None


def test_abandoned_tasks_do_not_reach_the_levels(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    course, record = stored_session(store, 3)
    finish_item(store, record, 1, GOOD)
    store.begin_item(user_id="u1", session_number=3, position=2, game_code=record["games"][1]["game_code"])
    store.finish_session("u1", reason="тест")
    codes = [item.game_code for item in store.passes(course)]
    assert codes == [record["games"][0]["game_code"]]


def test_the_pause_is_journaled(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    _, record = stored_session(store)
    store.pause("u1", position=3)
    store.resume("u1")
    store.pause("u1", position=None)
    store.finish_session("u1", reason="тест")
    first, second = record["pauses"]
    assert first["position"] == 3 and first["ended_by"] == "продолжение"
    assert second["ended_by"] == "завершение занятия"


def test_twelve_closed_sessions_finish_the_course(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    for number in range(1, COURSE_SESSIONS + 1):
        course, _ = stored_session(store, number)
        store.finish_session("u1", reason="тест")
    assert store.is_finished(course)
    assert course["finished_at"]

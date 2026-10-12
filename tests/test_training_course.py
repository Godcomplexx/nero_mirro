"""Курс тренировок: 12 занятий с одними заданиями, этапы, наборы, уровни форм.

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
    SESSION_PLANNED,
    CourseError,
    TrainingCourseStore,
)
from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening.difficulty_policy import FLAG_HARD, FormState, Success
from neuro_mirror.screening.training_course import (
    COURSE_SESSIONS,
    CoursePass,
    apply_levels,
    course_slots,
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


# ── Состав курса ──────────────────────────────────────────────────────────────

def composition() -> dict:
    return build_training_session(PROFILE, available_codes=implemented_game_codes())


def test_the_course_starts_with_a_simple_click_task():
    """Голос, перетаскивание и ведение курсора первыми не ставятся (5.2)."""
    first = get_game_definition(composition()["games"][0]["game_code"])
    assert first.response_type.value == "click"
    assert [m.value for m in first.modalities] == ["visual"]


def test_forms_with_levels_go_first_within_a_domain():
    """Формы без уровней берутся, только когда домену не хватает адаптивных."""
    memory = [game for game in composition()["games"] if game["domain"] == "Память"]
    assert all(game["adaptation"] == "adaptive" for game in memory)


def test_twelve_slots_hold_the_same_tasks():
    """Курс формируется сразу: во всех 12 занятиях одни и те же задания."""
    games = composition()["games"]
    slots = course_slots(games, "u1")
    assert len(slots) == COURSE_SESSIONS
    expected = [game["game_code"] for game in games]
    for slot in slots:
        assert [item["game_code"] for item in slot["games"]] == expected


def test_slots_differ_only_by_stimulus_set_and_seed():
    slots = course_slots(composition()["games"], "u1")
    assert [slot["games"][0]["stimulus_set_number"] for slot in slots] == [
        stimulus_set_number(n) for n in range(1, COURSE_SESSIONS + 1)
    ]
    assert slots[0]["games"][0]["randomization_seed"] != slots[1]["games"][0]["randomization_seed"]


def test_levels_are_set_per_form_when_a_session_opens():
    items = course_slots(composition()["games"], "u1")[6]["games"]
    apply_levels(items, {item["game_code"]: FormState(level=3) for item in items})
    for item in items:
        if item["adaptation"] == "adaptive":
            assert item["difficulty_level"] == 3
        else:
            assert item["difficulty_level"] is None


# ── Хранение курса ────────────────────────────────────────────────────────────

def new_course(store: TrainingCourseStore) -> dict:
    return store.create_course(
        user_id="u1", entry_session_id="moca-1", profile=PROFILE, composition=composition()
    )


def open_next(store: TrainingCourseStore, course: dict) -> dict:
    slot = store.next_slot(course)
    states, log = form_states(store.passes(course), slot["number"])
    return store.open_slot(course, slot, states=states, level_changes=log)


def stored_session(store: TrainingCourseStore, number: int = 1) -> tuple[dict, dict]:
    course = store.latest_course("u1") or new_course(store)
    while True:
        record = open_next(store, course)
        if record["number"] == number:
            return course, record
        store.finish_session("u1", reason="тест")


def finish_item(store: TrainingCourseStore, record: dict, position: int, result: Success | None) -> None:
    item = record["games"][position - 1]
    store.begin_item(user_id="u1", session_number=record["number"], position=position, game_code=item["game_code"])
    session_id = f"g{record['number']}-{position}"
    store.attach_game_session(
        user_id="u1", session_number=record["number"], position=position, game_session_id=session_id
    )
    store.record_outcome(
        game_session_id=session_id,
        completion_status="completed",
        technical_validity="valid",
        success=result,
        counted=result is not None,
        metrics={},
    )


def test_the_course_is_created_with_twelve_planned_slots(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    course = new_course(store)
    assert [slot["status"] for slot in course["sessions"]] == [SESSION_PLANNED] * COURSE_SESSIONS
    assert store.open_session("u1") is None


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


def test_correct_passes_raise_the_level_of_the_same_task_later(tmp_path):
    """Задания те же, сложность каждого растёт по правильности его прохождений."""
    store = TrainingCourseStore(tmp_path / "courses.json")
    course = new_course(store)
    for _ in range(5):
        record = open_next(store, course)
        for position in range(1, len(record["games"]) + 1):
            finish_item(store, record, position, GOOD if record["number"] >= 3 else OK)
    sixth = open_next(store, course)
    assert sixth["number"] == 6
    for item in sixth["games"]:
        expected = 2 if item["adaptation"] == "adaptive" else None
        assert item["difficulty_level"] == expected, item["game_code"]
    assert sixth["level_changes"]


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
    course = new_course(store)
    for _ in range(COURSE_SESSIONS):
        open_next(store, course)
        store.finish_session("u1", reason="тест")
    assert store.is_finished(course)
    assert store.next_slot(course) is None
    assert course["finished_at"]


def test_a_course_of_the_first_version_is_not_continued(tmp_path):
    """Курс без 12 слотов не продолжается — вместо него открывается новый."""
    import json

    path = tmp_path / "courses.json"
    path.write_text(json.dumps([{
        "course_id": "old", "user_id": "u1", "entry": {"session_id": "m", "profile": PROFILE},
        "sessions": [{"number": 1, "status": "in_progress", "games": []}],
    }]), encoding="utf-8")
    store = TrainingCourseStore(path)
    assert store.latest_course("u1") is None
    assert store.open_session("u1") is None
    new_course(store)
    assert store.latest_course("u1")["course_id"] != "old"

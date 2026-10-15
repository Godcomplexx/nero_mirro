"""Правила курса, добавленные по сверке с методикой.

«Методика подбора и оценки тренировочного курса» v2:

* 4.4 — порядок заданий с наименьшим взвешенным числом нарушений
  желательных правил, нарушения в плане; первое и последнее задания с 3-го
  занятия — посильные;
* 4.5, п. 5, 8 — продолжение после паузы с прерванной пробы, проба в журнале;
* 6.3 — причина прерывания, облегчённая альтернатива на временном уровне;
* 8.2, 8.3 — отчёты о занятии и о курсе;
* 9 — красные флаги, приостановка курса, уведомления специалисту.
"""
from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from neuro_mirror.core.next_step import next_step
from neuro_mirror.core.specialist_access import PIN_ENV
from neuro_mirror.core.user_profiles import UserProfileStore
from neuro_mirror.plugins.games.catalog import GAME_CATALOG, get_game_definition
from neuro_mirror.plugins.games.contracts import Domain, GameDefinition, Modality, ResponseType
from neuro_mirror.plugins.games.course_store import (
    ITEM_ABANDONED,
    ITEM_DONE,
    SESSION_COMPLETED,
    SESSION_INCOMPLETE,
    CourseError,
    TrainingCourseStore,
)
from neuro_mirror.plugins.games.registry import implemented_game_codes
from neuro_mirror.screening import course_report
from neuro_mirror.screening.difficulty_policy import FLAG_HARD, FormState, Success
from neuro_mirror.screening.dynamics import dynamics
from neuro_mirror.screening.session_order import (
    AFTER_HARD,
    RESPONSE_RUN,
    SAME_DOMAIN,
    SAME_MODALITY,
    arrange,
)
from neuro_mirror.screening.training_course import form_states, slot_items
from neuro_mirror.screening.training_plan import plan_session
from neuro_mirror.screening.training_safety import BY_CODE
from neuro_mirror.screening.training_session import build_training_session, lighter_alternative
from neuro_mirror.web.app import create_app

PROFILE = [
    {"domain": "Память", "score": 3, "max_score": 5},
    {"domain": "Внимание", "score": 4, "max_score": 5},
    {"domain": "Речь", "score": 2, "max_score": 3},
    {"domain": "Абстракция", "score": 1, "max_score": 2},
]


# ── Порядок заданий (4.4) ─────────────────────────────────────────────────────

def definition(code, domain, response, modalities=(Modality.VISUAL,)):
    return GameDefinition(
        code=code, slug=code.lower(), title=code, domains=(domain,), mechanics=(code,),
        modalities=tuple(modalities), response_type=response, stimulus_sets=("a",),
    )


def synthetic(*rows):
    defs = {row[0]: definition(*row) for row in rows}
    games = [{"game_code": code, "domain": defs[code].domains[0].value} for code in defs]
    return games, defs


def cost_of(order, defs, hard=frozenset()):
    """Стоимость порядка напрямую по правилам — для сверки с перебором."""
    total, run = 0, 1
    for a, b in zip(order, order[1:]):
        da, db = defs[a["game_code"]], defs[b["game_code"]]
        run = run + 1 if da.response_type == db.response_type else 1
        if run > 3:
            total += RESPONSE_RUN.weight
        same_modality = set(da.modalities) == set(db.modalities)
        if a["game_code"] in hard and b["game_code"] in hard and same_modality:
            total += AFTER_HARD.weight
        if a["domain"] == b["domain"]:
            total += SAME_DOMAIN.weight
        if same_modality:
            total += SAME_MODALITY.weight
    return total


def test_the_order_has_the_fewest_weighted_violations():
    """Порядок с наименьшей стоимостью — сверка с полным перебором."""
    games, defs = synthetic(
        ("A1", Domain.MEMORY, ResponseType.CLICK),
        ("A2", Domain.MEMORY, ResponseType.CLICK, (Modality.AUDITORY,)),
        ("B1", Domain.ATTENTION, ResponseType.CLICK),
        ("B2", Domain.ATTENTION, ResponseType.DRAG),
        ("C1", Domain.SPEECH, ResponseType.CLICK),
        ("D1", Domain.ABSTRACTION, ResponseType.CLICK, (Modality.AUDITORY, Modality.VISUAL)),
        ("D2", Domain.ABSTRACTION, ResponseType.CLICK),
    )
    ordered, note = arrange(games, defs, session_number=8, seed=1)
    best = min(cost_of(list(order), defs) for order in itertools.permutations(games))
    assert note["cost"] == best == cost_of(ordered, defs)


def test_no_run_of_more_than_three_answers_of_one_type_when_avoidable():
    games, defs = synthetic(*(
        [(f"K{i}", list(Domain)[i % 4], ResponseType.CLICK) for i in range(6)]
        + [("P1", Domain.ABSTRACTION, ResponseType.DRAG), ("P2", Domain.SPEECH, ResponseType.DRAG)]
    ))
    _, note = arrange(games, defs, session_number=8, seed=3)
    assert not [item for item in note["violations"] if item["rule"] == RESPONSE_RUN.id]


def test_every_violation_of_the_chosen_order_is_written_to_the_plan():
    games, defs = synthetic(*[(f"K{i}", Domain.MEMORY, ResponseType.CLICK) for i in range(5)])
    ordered, note = arrange(games, defs, session_number=8, seed=3)
    assert note["cost"] == sum(item["weight"] for item in note["violations"])
    run = [item for item in note["violations"] if item["rule"] == RESPONSE_RUN.id]
    assert [item["positions"] for item in run] == [[1, 2, 3, 4], [2, 3, 4, 5]]
    assert note["not_checked"], "правило о схеме выбора записано как непроверенное"


def test_after_a_hard_task_comes_an_easier_or_another_modality():
    games, defs = synthetic(
        ("GM-07", Domain.ATTENTION, ResponseType.CLICK),
        ("GM-04", Domain.MEMORY, ResponseType.CLICK),
        ("GM-17", Domain.ABSTRACTION, ResponseType.CLICK),
        ("X1", Domain.SPEECH, ResponseType.CLICK, (Modality.AUDITORY,)),
    )
    states = {"GM-07": FormState(level=3), "GM-04": FormState(level=3)}
    ordered, note = arrange(games, defs, session_number=8, seed=2, states=states)
    codes = [game["game_code"] for game in ordered]
    assert abs(codes.index("GM-07") - codes.index("GM-04")) != 1
    assert not [item for item in note["violations"] if item["rule"] == AFTER_HARD.id]


def test_ties_are_settled_by_the_seed_of_the_plan():
    games, defs = synthetic(*[(f"K{i}", list(Domain)[i], ResponseType.CLICK) for i in range(4)])
    first, _ = arrange(games, defs, session_number=8, seed=10)
    again, _ = arrange(games, defs, session_number=8, seed=10)
    assert first == again
    orders = {tuple(g["game_code"] for g in arrange(games, defs, session_number=8, seed=s)[0]) for s in range(20)}
    assert len(orders) > 1


def test_from_the_third_session_the_first_and_last_tasks_are_feasible():
    recent = {"GM-17": Success(10, 10), "GM-07": Success(9, 10), "GM-04": Success(3, 10)}
    session = build_training_session(
        PROFILE, session_number=3, recent=recent, order_seed=5, available_codes=implemented_game_codes(),
    )
    codes = [game["game_code"] for game in session["games"]]
    present = [code for code in ("GM-17", "GM-07", "GM-04") if code in codes]
    ranked = sorted(present, key=lambda code: -recent[code].correct / recent[code].total)
    assert codes[0] == ranked[0]
    assert codes[-1] == ranked[1]
    assert session["order"]["first"]["reason"].startswith("посильная")


def test_calibration_still_starts_with_a_simple_click_form():
    session = build_training_session(PROFILE, session_number=1, order_seed=7, available_codes=implemented_game_codes())
    first = get_game_definition(session["games"][0]["game_code"])
    assert first.response_type == ResponseType.CLICK and set(first.modalities) == {Modality.VISUAL}


# ── Облегчённая альтернатива (6.3) ────────────────────────────────────────────

def test_the_lighter_alternative_is_the_same_form_one_level_lower():
    item = {"domain": "Память", "domain_code": "memory", "game_code": "GM-04", "title": "x", "difficulty_level": 2}
    alternative = lighter_alternative(item, [item], available_codes=implemented_game_codes())
    assert alternative["game_code"] == "GM-04" and alternative["difficulty_level"] == 1


def test_at_level_one_the_alternative_is_another_form_of_the_domain():
    item = {"domain": "Память", "domain_code": "memory", "game_code": "GM-04", "title": "x", "difficulty_level": 1}
    alternative = lighter_alternative(item, [item], available_codes=implemented_game_codes())
    assert alternative["game_code"] != "GM-04"
    assert get_game_definition(alternative["game_code"]).primary_domain == Domain.MEMORY


# ── Хранение: прерывание, альтернатива, пауза, флаги ──────────────────────────

def open_course(tmp_path):
    store = TrainingCourseStore(tmp_path / "courses.json")
    course = store.create_course(user_id="u1", entry_session_id="m1", profile=PROFILE, plan=plan_session(PROFILE))
    slot = store.next_slot(course)
    games = build_training_session(PROFILE, session_number=1, available_codes=implemented_game_codes())["games"]
    store.open_slot(course, slot, games=games, states={}, level_changes=[])
    return store, course


def start(store, position, game_session_id):
    item = store.open_session("u1")["games"][position - 1]
    store.begin_item(user_id="u1", session_number=1, position=position, game_code=item["game_code"])
    store.attach_game_session(user_id="u1", session_number=1, position=position, game_session_id=game_session_id)
    return item


def finish(store, game_session_id, success=Success(8, 10)):
    store.record_outcome(
        game_session_id=game_session_id, completion_status="completed", technical_validity="valid",
        success=success, counted=True, metrics={}, u06_status="completed_success", end_reason="done",
    )


def test_an_interrupted_task_keeps_its_reason(tmp_path):
    store, _ = open_course(tmp_path)
    start(store, 1, "g1")
    item = store.interrupt_item("u1", position=1, reason=BY_CODE["too_hard"].to_dict())
    assert item["status"] == ITEM_ABANDONED
    assert item["interruption_reason"]["code"] == "too_hard"


def test_the_alternative_stands_right_after_and_does_not_reach_the_levels(tmp_path):
    store, course = open_course(tmp_path)
    original = start(store, 1, "g1")
    store.interrupt_item("u1", position=1, reason=BY_CODE["too_hard"].to_dict())
    [alt] = slot_items([{**original, "difficulty_level": None}], "u1", 1)
    added = store.add_alternative("u1", position=1, alternative={**alt, "temporary_level": True})
    games = store.open_session("u1")["games"]
    assert games[1] is added or games[1]["position"] == added["position"]
    assert games[0]["replaced_by"] == added["position"]
    store.begin_item(user_id="u1", session_number=1, position=added["position"], game_code=added["game_code"])
    store.attach_game_session(user_id="u1", session_number=1, position=added["position"], game_session_id="alt")
    finish(store, "alt", Success(10, 10))
    done = next(row for row in store.open_session("u1")["games"] if row["position"] == added["position"])
    assert done["status"] == ITEM_DONE and done["counted"] is False
    assert all(item.game_code != added["game_code"] or item.result is None for item in store.passes(course))


def test_a_task_replaced_by_a_done_alternative_does_not_make_the_session_incomplete(tmp_path):
    store, course = open_course(tmp_path)
    session = store.open_session("u1")
    for position in range(2, len(session["games"]) + 1):
        start(store, position, f"g{position}")
        finish(store, f"g{position}")
    original = start(store, 1, "g1")
    store.interrupt_item("u1", position=1, reason=BY_CODE["too_hard"].to_dict())
    [alt] = slot_items([original], "u1", 1)
    added = store.add_alternative("u1", position=1, alternative=alt)
    store.begin_item(user_id="u1", session_number=1, position=added["position"], game_code=added["game_code"])
    store.attach_game_session(user_id="u1", session_number=1, position=added["position"], game_session_id="alt")
    finish(store, "alt")
    assert course["sessions"][0]["status"] == SESSION_COMPLETED


def test_the_pause_journal_names_the_trial(tmp_path):
    store, _ = open_course(tmp_path)
    record = store.pause("u1", position=3, trial=4)
    assert record["position"] == 3 and record["trial"] == 4


def test_only_the_started_task_with_its_game_session_is_resumed(tmp_path):
    store, _ = open_course(tmp_path)
    start(store, 1, "g1")
    item = store.resume_item(user_id="u1", session_number=1, position=1, game_session_id="g1")
    assert item["resumed"] == 1 and item["attempts"] == 1
    with pytest.raises(CourseError):
        store.resume_item(user_id="u1", session_number=1, position=1, game_session_id="other")
    with pytest.raises(CourseError):
        store.resume_item(user_id="u1", session_number=1, position=2, game_session_id="g1")


def test_ending_the_session_writes_the_reason_to_the_abandoned_task(tmp_path):
    store, _ = open_course(tmp_path)
    start(store, 1, "g1")
    session = store.finish_session("u1", reason="устал", interruption=BY_CODE["fatigue"].to_dict())
    assert session["status"] == SESSION_INCOMPLETE
    assert session["games"][0]["interruption_reason"]["code"] == "fatigue"


def test_a_red_flag_holds_the_course_until_released(tmp_path):
    store, course = open_course(tmp_path)
    store.raise_red_flag("u1", source="pre_session_check", detail="новые симптомы")
    assert course["hold"] and course["red_flags"][0]["session_number"] == 1
    released = store.release_hold("u1", note="осмотрен")
    assert released["released_at"] and course["hold"] is None
    assert store.release_hold("u1") is None


# ── Маршруты ──────────────────────────────────────────────────────────────────

def moca_report():
    return {"session_id": "m1", "stored_at": "2026-10-01T10:00:00+00:00", "report_type": "moca",
            "domains": {"moca_domains": PROFILE}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(PIN_ENV, "4821")
    users = UserProfileStore(tmp_path)
    user = users.create_user("Test", consent=True, personal_data_consent=True,
                             audio_data_consent=True, video_data_consent=True)
    users.select_user(user["id"])
    sent = []
    replies = {"resume_ok": True}

    async def request(event, timeout=None):
        sent.append(event)
        if event.topic.startswith("req.game."):
            action = event.payload.get("action")
            if action == "pause":
                return {"ok": True, "paused": True, "trial": 3}
            if action == "resume":
                return {"ok": replies["resume_ok"], "session_id": event.payload["session_id"], "resumed": True,
                        "message": "Игровая сессия не найдена."}
            return {"ok": True, "session_id": "game-1", "finished": False}
        return {"items": [moca_report()]}

    app = create_app()
    app.state.context = SimpleNamespace(
        user_store=users,
        runtime=SimpleNamespace(
            bus=SimpleNamespace(request=request),
            game_history_store=SimpleNamespace(for_user=lambda _user_id: ()),
            session_store=SimpleNamespace(list_for_user=lambda _user_id: []),
            training_course_store=TrainingCourseStore(tmp_path / "courses.json"),
        ),
    )
    test_client = TestClient(app)
    test_client.sent = sent
    test_client.replies = replies
    test_client.store = app.state.context.runtime.training_course_store
    test_client.user_id = user["id"]
    yield test_client
    test_client.close()


def started(client):
    body = client.get("/api/training/session").json()
    game = body["games"][0]
    client.post(f"/api/games/{game['game_code']}/start", json={"course_session": 1, "course_position": 1})
    return body, game


def test_the_session_carries_the_order_the_reasons_and_the_question(client):
    body = client.get("/api/training/session").json()
    assert body["order"]["seed"] and "violations" in body["order"]
    assert {reason["code"] for reason in body["interruption_reasons"]} >= {"fatigue", "symptoms"}
    assert body["pre_check_question"]["status"] == "draft"


def test_the_pause_asks_the_game_for_the_trial(client):
    _, game = started(client)
    record = client.post("/api/training/session/pause", json={
        "position": 1, "game_code": game["game_code"], "game_session_id": "game-1",
    }).json()
    assert record["trial"] == 3
    assert client.sent[-1].payload == {"session_id": "game-1", "action": "pause"}


def test_a_paused_task_resumes_from_its_trial(client):
    _, game = started(client)
    reply = client.post(f"/api/games/{game['game_code']}/resume",
                        json={"session_id": "game-1", "course_session": 1, "course_position": 1})
    assert reply.status_code == 200 and reply.json()["resumed"] is True
    item = client.store.open_session(client.user_id)["games"][0]
    assert item["resumed"] == 1 and item["attempts"] == 1


def test_a_task_that_cannot_resume_answers_409(client):
    _, game = started(client)
    client.replies["resume_ok"] = False
    reply = client.post(f"/api/games/{game['game_code']}/resume", json={"session_id": "lost"})
    assert reply.status_code == 409


def test_fatigue_offers_to_end_the_session_first(client):
    started(client)
    reply = client.post("/api/training/session/interrupt", json={"position": 1, "reason": "fatigue"}).json()
    assert reply["stopped"] is False and reply["suggest"] == "finish"


def test_a_hard_task_offers_a_lighter_alternative(client):
    body, game = started(client)
    reply = client.post("/api/training/session/interrupt", json={"position": 1, "reason": "too_hard"}).json()
    assert reply["suggest"] == "alternative" and reply["alternative"]
    session = client.post("/api/training/session/alternative", json={"position": 1}).json()
    assert len(session["games"]) == len(body["games"]) + 1
    alternative = session["games"][1]
    assert alternative["alternative_for"] == 1 and alternative["temporary_level"] is True
    assert alternative["domain"] == game["domain"]


def test_new_symptoms_stop_the_session_and_hold_the_course(client):
    started(client)
    reply = client.post("/api/training/session/interrupt", json={"position": 1, "reason": "symptoms"}).json()
    assert reply["stopped"] is True and "врачу" in reply["message"]
    held = client.get("/api/training/session")
    assert held.status_code == 409 and held.headers["X-Course-Hold"] == "1"
    assert client.post("/api/specialist/course/release", json={}).status_code == 403
    client.post("/api/specialist/login", json={"pin": "4821"})
    report = client.get("/api/specialist/report").json()
    assert {item["kind"] for item in report["notifications"]} >= {"red_flag", "hold"}
    assert client.post("/api/specialist/course/release", json={}).status_code == 200
    assert client.get("/api/training/session").status_code == 200


def test_yes_to_the_question_before_the_session_holds_the_course(client):
    client.get("/api/training/session")
    assert client.post("/api/training/session/check", json={"new_symptoms": False}).json() == {"stop": False}
    reply = client.post("/api/training/session/check", json={"new_symptoms": True}).json()
    assert reply["stop"] is True
    assert client.get("/api/training/session").status_code == 409
    # Занятие не израсходовано: после снятия приостановки оно продолжается
    session = client.store.open_session(client.user_id)
    assert session["number"] == 1 and session["status"] == "in_progress"


def test_ending_with_a_reason_is_written_down(client):
    started(client)
    body = client.post("/api/training/session/finish", json={"reason_code": "wellbeing"}).json()
    assert body["status"] == "incomplete" and body["message"] == ""
    course = client.get("/api/training/course").json()
    assert course["sessions"][0]["games"][0]["interruption_reason"]["code"] == "wellbeing"
    assert "Плохое самочувствие" in course["sessions"][0]["end_reason"]


# ── Отчёты (8.2, 8.3) и уведомления (9) ───────────────────────────────────────

def item(code, *, number, status="done", level=1, success=(8, 10), set_number=1, counted=True, domain="Внимание", **extra):
    return {
        "game_code": code, "title": code, "domain": domain, "position": extra.pop("position", 1),
        "status": status, "difficulty_level": level, "stimulus_set_number": set_number,
        "success": {"correct": success[0], "total": success[1]} if success else None,
        "counted": counted, **extra,
    }


def course_of(*sessions, red_flags=(), hold=None):
    return {
        "course_id": "c1",
        "entry": {"session_id": "m1", "profile": PROFILE},
        "sessions": [
            {"number": number, "status": status, "games": list(games), "pauses": []}
            for number, status, games in sessions
        ],
        "red_flags": list(red_flags),
        "hold": hold,
    }


def test_the_session_report_has_active_time_early_completion_and_feeling():
    session = {
        "number": 2,
        "games": [item("GM-01", number=2, position=1, started_at="2026-10-01T10:00:00+00:00",
                       finished_at="2026-10-01T10:05:00+00:00", time_limit_ms=240000, end_reason="done",
                       u06_status="completed_success")],
        "pauses": [{"position": 1, "trial": 2, "paused_at": "2026-10-01T10:01:00+00:00",
                    "ended_at": "2026-10-01T10:02:00+00:00", "ended_by": "продолжение"}],
    }
    san = [{"session_id": "c1-2", "moment": "before", "groups": []}]
    report = course_report.session_report(session, san, "c1")
    game = report["games"][0]
    assert game["active_seconds"] == 240.0
    assert game["early_completion"]["early"] is True
    assert report["pause_seconds"] == 60.0 and report["pauses"][0]["trial"] == 2
    assert report["san_before"] is san[0] and report["san_after"] is None


def test_six_and_twelve_are_compared_only_on_one_level_and_set_three():
    course = course_of(
        (6, "completed", [item("GM-07", number=6, set_number=3, success=(6, 10)),
                          item("GM-17", number=6, set_number=3, level=1),
                          item("GM-09", number=6, set_number=3)]),
        (12, "completed", [item("GM-07", number=12, set_number=3, success=(9, 10)),
                           item("GM-17", number=12, set_number=3, level=2)]),
    )
    result = course_report.compare_6_and_12(course)
    assert [row["game_code"] for row in result["rows"]] == ["GM-07"]
    reasons = {row["game_code"]: row["reason"] for row in result["not_comparable"]}
    assert "разный уровень" in reasons["GM-17"] and "12" in reasons["GM-09"]


def test_the_course_report_counts_moca_analogs_and_deficit():
    course = course_of((1, "completed", [item("GM-11", number=1), item("GM-16", number=1, domain="Речь"),
                                         item("GM-11", number=1, status="abandoned")]))
    summary = course_report.course_summary(course)
    passes = {row["game_code"]: row["passes"] for row in summary["moca_analogs"]}
    assert passes == {"GM-11": 1, "GM-13": 0, "GM-16": 1, "GM-24": 0}
    assert {row["domain"]: row["deficit"] for row in summary["deficit"]}["Память"] == 0.4
    assert "не изменение когнитивного статуса" in summary["note"]


def test_more_than_two_incomplete_sessions_notify_the_specialist():
    course = course_of(*[(n, "incomplete", []) for n in (1, 2, 3)])
    kinds = [row["kind"] for row in course_report.notifications(course)]
    assert "incomplete_sessions" in kinds
    assert "incomplete_sessions" not in [row["kind"] for row in course_report.notifications(course_of(*[(n, "incomplete", []) for n in (1, 2)]))]


def test_all_forms_of_a_domain_marked_hard_notify_the_specialist():
    speech = [definition.code for definition in GAME_CATALOG
              if definition.primary_domain == Domain.SPEECH and definition.code in ("GM-14",)]
    levels = {code: {"level": 1, "flags": [FLAG_HARD]} for code in speech}
    kinds = [row["kind"] for row in course_report.notifications(course_of(), levels)]
    assert "domain_hard" in kinds


def test_a_sustained_drop_across_domains_notifies_the_specialist():
    def falling(code, domain):
        return [
            (number, item(code, number=number, domain=domain, success=(score, 10)))
            for number, score in ((7, 9), (8, 7), (9, 5))
        ]
    rows = falling("GM-07", "Внимание") + falling("GM-04", "Память")
    sessions = {}
    for number, row in rows:
        sessions.setdefault(number, []).append(row)
    course = course_of(*[(number, "completed", games) for number, games in sorted(sessions.items())])
    notices = course_report.notifications(course)
    assert "sustained_drop" in [row["kind"] for row in notices]
    one_domain = course_of(*[(n, "completed", [g]) for n, g in falling("GM-07", "Внимание")])
    assert "sustained_drop" not in [row["kind"] for row in course_report.notifications(one_domain)]


def test_growth_after_analog_forms_carries_a_learning_note():
    def moca(session_id, at, attention):
        return {"report_type": "moca", "session_id": session_id, "stored_at": at, "scenario_version": "1",
                "domains": {"moca_score": attention, "moca_max_score": 15,
                            "moca_domains": [{"domain": "Внимание", "score": attention, "max_score": 5}]}}
    items = [moca("m1", "2026-10-01T10:00:00+00:00", 3), moca("m2", "2026-11-20T10:00:00+00:00", 5)]
    analogs = [{"game_code": "GM-11", "domain": "Внимание", "passes": 4}]
    result = dynamics(items, entry_session_id="m1", moca_analogs=analogs)["moca"]
    assert result["learning_notes"] and "GM-11 — 4" in result["learning_notes"][0]
    assert dynamics(items, entry_session_id="m1")["moca"]["learning_notes"] == []


def test_a_held_course_is_the_next_step():
    step = next_step({"screening_done": True, "moca_done": True}, course={"hold": {"since": "x"}})
    assert step["step"] == "hold"

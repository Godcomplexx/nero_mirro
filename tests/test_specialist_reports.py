"""Разграничение отчётов пользователя и специалиста (ТЗ, модуль отчётности).

Пользователю — краткий отчёт без балла и интерпретации HADS и без речевых
маркеров; специалисту по PIN — расширенный: баллы, домены, маркеры,
качество данных, журнал событий, HADS, тренировки.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from neuro_mirror.core.specialist_access import (
    IDLE_TIMEOUT,
    MAX_FAILED_ATTEMPTS,
    SpecialistAccess,
    SpecialistAccessError,
)
from neuro_mirror.screening.report_views import (
    SPEECH_RESEARCH_NOTE,
    specialist_report,
    user_results,
    user_view,
)

HADS_REPORT = {
    "report_type": "screening",
    "session_id": "scr-1",
    "stored_at": "2026-10-10T08:00:00+00:00",
    "domains": {
        "heart_rate_bpm": 72.0,
        "hads_anxiety_score": 11,
        "hads_anxiety_max": 21,
        "hads_depression_score": 4,
        "hads_depression_max": 21,
        "hads_answered_count": 14,
        "hads_question_count": 14,
        "video_quality_issues": [{"code": "no_face"}],
    },
    "summary": {
        "hads_anxiety_interpretation": "клинически выраженная тревога",
        "hads_depression_interpretation": "норма депрессия",
        "hads_notes": "",
        "limitations": "Результат может быть ограничен условиями прохождения: фоновый шум.",
    },
    "sources": {"hads": {"answers": [{"question": "Я испытываю напряжение", "option_text": "часто", "score": 2}]}},
}

MOCA_REPORT = {
    "report_type": "moca",
    "session_id": "moca-1",
    "stored_at": "2026-10-11T08:00:00+00:00",
    "domains": {
        "moca_score": 10,
        "moca_max_score": 15,
        "moca_domains": [{"domain": "Память", "score": 3, "max_score": 5, "deficit": 0.4}],
        "moca_speech_summary": {"words_per_minute": 96.4},
        "moca_tasks": [
            {"task_id": "delayed_recall", "domain": "Память", "score": 3, "max_score": 5, "transcript": "лицо бархат церковь"},
            {"task_id": "abstraction_1", "domain": "Абстракция", "score": 0, "max_score": 1, "transcript": ""},
        ],
        "some_future_marker": 0.5,
    },
    "summary": {"moca_interpretation": "Промежуточный результат voice-MoCA", "limitations": ""},
}


# ── Что видит пользователь ────────────────────────────────────────────────────

def test_the_user_does_not_see_the_hads_score_or_interpretation():
    view = user_view(HADS_REPORT)
    text = json.dumps(view, ensure_ascii=False)
    assert "hads_anxiety_score" not in text
    assert "hads_depression_score" not in text
    assert "тревога" not in text
    assert "sources" not in view
    assert view["domains"]["hads_answered_count"] == 14


def test_the_user_sees_the_limitation_of_the_result():
    assert user_view(HADS_REPORT)["summary"]["limitations"].startswith("Результат может быть ограничен")


def test_the_user_sees_the_moca_score_and_domains_but_not_speech_markers():
    view = user_view(MOCA_REPORT)
    assert view["domains"]["moca_score"] == 10
    assert view["domains"]["moca_domains"]
    assert "moca_speech_summary" not in view["domains"]
    assert "moca_tasks" not in view["domains"]
    assert "moca_interpretation" not in view["summary"]


def test_a_new_report_field_does_not_reach_the_user_by_default():
    assert "some_future_marker" not in user_view(MOCA_REPORT)["domains"]


def test_wellbeing_answers_and_game_results_stay_with_the_specialist():
    items = [HADS_REPORT, {"report_type": "san_survey"}, {"report_type": "training_game"}]
    assert [item["report_type"] for item in user_results(items)] == ["screening"]


# ── Что видит специалист ──────────────────────────────────────────────────────

def specialist(**kwargs):
    return specialist_report([MOCA_REPORT, HADS_REPORT], sessions=kwargs.pop("sessions", []), **kwargs)


def test_the_specialist_sees_hads_scores_interpretation_and_answers():
    hads = specialist()["hads"][0]
    assert hads["anxiety"] == {"score": 11, "max_score": 21, "interpretation": "клинически выраженная тревога"}
    assert hads["answers"][0]["option_text"] == "часто"


def test_the_specialist_sees_moca_tasks_markers_and_data_quality():
    moca = specialist()["moca"][0]
    assert moca["interpretation"].startswith("Промежуточный")
    assert [task["task_id"] for task in moca["tasks"]] == ["delayed_recall", "abstraction_1"]
    assert moca["speech_markers"]["note"] == SPEECH_RESEARCH_NOTE
    assert moca["speech_markers"]["values"]["words_per_minute"] == 96.4
    assert moca["quality"]["unrecognized_answers"] == 1


def test_the_specialist_sees_the_event_journal():
    sessions = [{"session_id": "s", "scenario": "hads", "status": "interrupted", "interruption_reason": "stop",
                 "events": [{"timestamp": "t", "type": "session_started", "details": {}}]}]
    journal = specialist(sessions=sessions)["journal"]
    assert journal[0]["interruption_reason"] == "stop"
    assert journal[0]["events"][0]["type"] == "session_started"


def test_the_specialist_sees_the_training_course():
    course = {"course_id": "c", "plan": {"Память": 4}, "entry": {"session_id": "moca-1"},
              "sessions": [{"number": 1, "stage": "calibration", "status": "completed",
                            "games": [{"position": 1, "game_code": "GM-01", "status": "done",
                                       "success": {"correct": 9, "total": 10}}], "pauses": []}]}
    training = specialist(course=course, levels={"GM-01": {"level": 1, "flags": []}})["training"]
    assert training["sessions"][0]["done"] == 1
    assert training["sessions"][0]["games"][0]["success"] == {"correct": 9, "total": 10}
    assert "не изменение когнитивного статуса" in training["note"]


# ── Доступ по PIN ─────────────────────────────────────────────────────────────

class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)

    def __call__(self):
        return self.now


def test_the_pin_is_stored_only_as_a_hash(tmp_path):
    access = SpecialistAccess(tmp_path / "specialist.json")
    access.set_pin("4821")
    assert "4821" not in (tmp_path / "specialist.json").read_text(encoding="utf-8")
    assert access.is_active()


@pytest.mark.parametrize("pin", ["", "12", "123456789", "12a4"])
def test_a_pin_must_be_four_to_eight_digits(tmp_path, pin):
    with pytest.raises(SpecialistAccessError):
        SpecialistAccess(tmp_path / "specialist.json").set_pin(pin)


def test_the_pin_cannot_be_set_twice(tmp_path):
    access = SpecialistAccess(tmp_path / "specialist.json")
    access.set_pin("4821")
    with pytest.raises(SpecialistAccessError):
        SpecialistAccess(tmp_path / "specialist.json").set_pin("1111")


def test_a_wrong_pin_does_not_open_the_mode(tmp_path):
    SpecialistAccess(tmp_path / "specialist.json").set_pin("4821")
    access = SpecialistAccess(tmp_path / "specialist.json")
    with pytest.raises(SpecialistAccessError):
        access.login("0000")
    assert not access.is_active()
    access.login("4821")
    assert access.is_active()


def test_too_many_wrong_pins_lock_the_entry(tmp_path):
    SpecialistAccess(tmp_path / "specialist.json").set_pin("4821")
    access = SpecialistAccess(tmp_path / "specialist.json")
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(SpecialistAccessError):
            access.login("0000")
    with pytest.raises(SpecialistAccessError, match="Слишком много"):
        access.login("4821")


def test_the_mode_closes_by_itself_when_left_idle(tmp_path):
    clock = Clock()
    access = SpecialistAccess(tmp_path / "specialist.json", clock=clock)
    access.set_pin("4821")
    clock.now += IDLE_TIMEOUT - timedelta(seconds=1)
    assert access.is_active(), "обращение продлевает режим"
    clock.now += IDLE_TIMEOUT + timedelta(seconds=1)
    assert not access.is_active()


def test_the_pin_is_changed_only_from_the_open_mode(tmp_path):
    access = SpecialistAccess(tmp_path / "specialist.json")
    access.set_pin("4821")
    access.logout()
    with pytest.raises(SpecialistAccessError):
        access.change_pin("1357")
    access.login("4821")
    access.change_pin("1357")
    access.logout()
    access.login("1357")


# ── Маршруты ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    from neuro_mirror.core import specialist_access as access_module
    from neuro_mirror.core.user_profiles import UserProfileStore
    from neuro_mirror.plugins.games.course_store import TrainingCourseStore
    from neuro_mirror.web.app import create_app

    monkeypatch.setattr(access_module, "DEFAULT_PATH", tmp_path / "specialist.json")
    users = UserProfileStore(tmp_path)
    user = users.create_user("Test", consent=True, personal_data_consent=True,
                             audio_data_consent=True, video_data_consent=True)
    users.select_user(user["id"])

    async def request(event, timeout=None):
        return {"items": [dict(MOCA_REPORT), dict(HADS_REPORT)]}

    app = create_app()
    app.state.context = SimpleNamespace(
        user_store=users,
        runtime=SimpleNamespace(
            bus=SimpleNamespace(request=request),
            session_store=SimpleNamespace(list_for_user=lambda _user_id: []),
            training_course_store=TrainingCourseStore(tmp_path / "courses.json"),
        ),
    )
    test_client = TestClient(app)
    yield test_client
    test_client.close()


def test_results_for_the_user_carry_no_hads_score(client):
    body = client.get("/api/results").json()
    text = json.dumps(body, ensure_ascii=False)
    assert "hads_anxiety_score" not in text and "клинически" not in text
    assert body["recommendation"]


def test_the_specialist_report_is_closed_without_the_pin(client):
    assert client.get("/api/specialist/report").status_code == 403
    assert client.get("/api/specialist/status").json() == {"configured": False, "active": False}


def test_the_specialist_report_opens_after_the_pin(client):
    assert client.post("/api/specialist/setup", json={"pin": "4821"}).status_code == 200
    report = client.get("/api/specialist/report").json()
    assert report["hads"][0]["anxiety"]["score"] == 11
    assert report["moca"][0]["tasks"]
    client.post("/api/specialist/logout")
    assert client.get("/api/specialist/report").status_code == 403
    assert client.post("/api/specialist/login", json={"pin": "0000"}).status_code == 403
    assert client.post("/api/specialist/login", json={"pin": "4821"}).status_code == 200

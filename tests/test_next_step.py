"""Какой сценарий система предлагает следующим (ТЗ 5.4.8; ПМИ 1.30, 1.31).

Новому пользователю — первичное обследование: базовый скрининг, затем
аудио-MoCA. С завершённым обследованием — тренировки. После курса —
повторное обследование. Отчёты доступны независимо от предложения.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from neuro_mirror.core.next_step import next_step

SCREENED = {"screening_done": True}
TESTED = {"screening_done": True, "moca_done": True, "last_moca_at": "2026-10-01T10:00:00+00:00"}


def test_a_new_user_is_offered_the_basic_screening_first():
    step = next_step({})
    assert step["step"] == "screening"
    assert step["section"] == "screening"
    assert "когнитивный тест" in step["text"]


def test_after_the_screening_comes_the_cognitive_test():
    step = next_step(SCREENED)
    assert (step["step"], step["section"]) == ("moca", "moca")


def test_with_the_test_done_the_training_is_offered():
    step = next_step(TESTED)
    assert (step["step"], step["section"]) == ("training", "training")
    assert step["action"] == "Начать тренировку"


def test_a_course_in_progress_names_the_next_session():
    course = {"finished_at": None}
    step = next_step(TESTED, course=course, completed_sessions=3, sessions_total=12)
    assert "занятие 4 из 12" in step["text"]
    assert step["action"] == "Продолжить тренировку"


def test_after_the_course_the_test_is_repeated():
    course = {"finished_at": "2026-11-20T10:00:00+00:00"}
    step = next_step(TESTED, course=course, completed_sessions=12)
    assert (step["step"], step["section"]) == ("exit_screening", "moca")


def test_a_test_taken_after_the_course_opens_a_new_one():
    course = {"finished_at": "2026-11-20T10:00:00+00:00"}
    progress = {**TESTED, "last_moca_at": "2026-11-25T10:00:00+00:00"}
    assert next_step(progress, course=course, completed_sessions=12)["step"] == "training"


def test_reports_stay_available_whatever_is_suggested():
    for progress in ({}, SCREENED, TESTED):
        assert "«Отчёты»" in next_step(progress)["reports_note"]


def test_the_endpoint_answers_for_the_active_user(tmp_path):
    from neuro_mirror.core.user_profiles import UserProfileStore
    from neuro_mirror.plugins.games.course_store import TrainingCourseStore
    from neuro_mirror.web.app import create_app

    users = UserProfileStore(tmp_path)
    user = users.create_user("Test", consent=True, personal_data_consent=True,
                             audio_data_consent=True, video_data_consent=True)
    users.select_user(user["id"])
    app = create_app()
    app.state.context = SimpleNamespace(
        user_store=users,
        runtime=SimpleNamespace(training_course_store=TrainingCourseStore(tmp_path / "courses.json")),
    )
    client = TestClient(app)
    assert client.get("/api/next-step").json()["step"] == "screening"
    users.update_progress(user["id"], screening_done=True, moca_done=True)
    assert client.get("/api/next-step").json()["step"] == "training"
    client.close()

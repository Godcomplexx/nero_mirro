from __future__ import annotations

import json

import pytest

from neuro_mirror.screening.situational_task import (
    FINAL_STEP,
    SituationalTaskError,
    advance,
    initial_checkpoint,
    load_demo_narrative,
    public_state,
    result_from_checkpoint,
    score_demo,
)
from neuro_mirror.screening.report_views import specialist_report


def narrative() -> dict:
    return {
        "id": "demo-test-01",
        "title": "Тест",
        "demo_only": True,
        "enabled_in_screening": False,
        "image": "demo.png",
        "story": "Короткая история.",
        "orientation_questions": [
            {"question": f"Ориентация {i}", "expected_answer": "ответ"}
            for i in range(4)
        ],
        "image_questions": ["Риск?", "Решение?", "Первое действие?", "К кому обратиться?"],
        "memory_questions": [
            {"question": f"Память {i}", "expected_answer": "ответ"}
            for i in range(4)
        ],
        "scoring": {"recall_units": []},
    }


def test_loader_accepts_only_disabled_demo_content(tmp_path):
    item = narrative()
    path = tmp_path / "demo_test_01.json"
    path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    assert load_demo_narrative("demo-test-01", directory=tmp_path)["demo_only"] is True

    item["enabled_in_screening"] = True
    path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SituationalTaskError):
        load_demo_narrative("demo-test-01", directory=tmp_path)


@pytest.mark.parametrize(
    ("narrative_id", "form", "image"),
    [
        ("sbs-pam-01", "entry", "sbs_pam_01.jpeg"),
        ("sbs-pam-02", "exit", "sbs_pam_02.jpeg"),
        ("sbs-pam-03", "backup", "sbs_pam_03.jpeg"),
    ],
)
def test_memory_narrative_passports_are_complete(narrative_id, form, image):
    item = load_demo_narrative(narrative_id)
    assert item["form"] == form
    assert item["image"] == image
    assert len(item["orientation_questions"]) == 4
    assert len(item["image_questions"]) == 4
    assert len(item["memory_questions"]) == 4
    assert len(item["scoring"]["recall_units"]) == 10
    assert len(item["scoring"]["image_concepts"]) == 7


def test_story_is_exposed_only_on_the_listening_step():
    item = narrative()
    checkpoint = initial_checkpoint(item["id"])
    session = {"session_id": "s1", "status": "in_progress", "checkpoint": checkpoint}
    assert "story" not in public_state(session, item)
    checkpoint, _ = advance(checkpoint, item, action="begin")
    checkpoint, _ = advance(checkpoint, item, action="continue_now")
    checkpoint, _ = advance(checkpoint, item, action="glasses_ready")
    checkpoint, _ = advance(checkpoint, item, action="hearing_good")
    session["checkpoint"] = checkpoint
    assert public_state(session, item)["story"] == item["story"]
    checkpoint, _ = advance(checkpoint, item, action="story_heard")
    session["checkpoint"] = checkpoint
    assert "story" not in public_state(session, item)


def test_full_demo_flow_has_checkpoints_but_no_total_score():
    item = narrative()
    checkpoint = initial_checkpoint(item["id"])
    checkpoint, _ = advance(checkpoint, item, action="begin")
    checkpoint, _ = advance(checkpoint, item, action="continue_now")
    checkpoint, _ = advance(checkpoint, item, action="glasses_ready")
    checkpoint, _ = advance(checkpoint, item, action="hearing_good")
    checkpoint, _ = advance(checkpoint, item, action="story_heard")
    checkpoint, _ = advance(checkpoint, item, action="submit_retelling", value="Пересказ")
    checkpoint, _ = advance(checkpoint, item, action="skip_retelling_addition")
    for _ in item["orientation_questions"]:
        checkpoint, _ = advance(checkpoint, item, action="submit_answer", value="Ответ")
    checkpoint, _ = advance(
        checkpoint, item, action="submit_image_description", value="Описание"
    )
    checkpoint, _ = advance(checkpoint, item, action="skip_image_description_addition")
    for _ in item["image_questions"]:
        checkpoint, _ = advance(checkpoint, item, action="submit_answer", value="Ответ")
    completed = False
    for index, _ in enumerate(item["memory_questions"]):
        checkpoint, completed = advance(
            checkpoint, item, action="submit_answer", value="Ответ"
        )
        assert completed is (index == len(item["memory_questions"]) - 1)

    assert completed is True
    assert checkpoint["step"] == FINAL_STEP
    result = result_from_checkpoint(checkpoint)
    assert result["demo_only"] is True
    assert result["has_total_score"] is False
    assert result["specialist_confirmation_required"] is True
    assert len(result["responses"]["orientation"]) == 4
    assert len(result["responses"]["memory"]) == 4


def test_empty_answer_does_not_advance():
    item = narrative()
    checkpoint = initial_checkpoint(item["id"])
    checkpoint, _ = advance(checkpoint, item, action="begin")
    checkpoint, _ = advance(checkpoint, item, action="continue_now")
    checkpoint, _ = advance(checkpoint, item, action="glasses_ready")
    checkpoint, _ = advance(checkpoint, item, action="hearing_good")
    checkpoint, _ = advance(checkpoint, item, action="story_heard")
    with pytest.raises(SituationalTaskError, match="Введите"):
        advance(checkpoint, item, action="submit_retelling", value="  ")


def test_preparation_can_be_deferred_before_story():
    item = narrative()
    checkpoint, _ = advance(initial_checkpoint(item["id"]), item, action="begin")
    checkpoint, completed = advance(checkpoint, item, action="defer")
    assert completed is True
    result = result_from_checkpoint(checkpoint, item)
    assert result["outcome"] == "deferred"
    assert result["specialist_confirmation_required"] is False
    assert "preliminary_scores" not in result


def test_second_bad_hearing_check_stops_attempt():
    item = narrative()
    checkpoint, _ = advance(initial_checkpoint(item["id"]), item, action="begin")
    checkpoint, _ = advance(checkpoint, item, action="continue_now")
    checkpoint, _ = advance(checkpoint, item, action="glasses_ready")
    checkpoint, completed = advance(checkpoint, item, action="hearing_bad")
    assert completed is False
    checkpoint, completed = advance(checkpoint, item, action="hearing_bad")
    assert completed is True
    assert result_from_checkpoint(checkpoint, item)["outcome"] == "not_conducted"


def test_prompt_ladder_is_recorded_with_the_answer():
    item = narrative()
    checkpoint = initial_checkpoint(item["id"])
    checkpoint, _ = advance(checkpoint, item, action="begin")
    checkpoint, _ = advance(checkpoint, item, action="continue_now")
    checkpoint, _ = advance(checkpoint, item, action="glasses_ready")
    checkpoint, _ = advance(checkpoint, item, action="hearing_good")
    checkpoint, _ = advance(checkpoint, item, action="story_heard")
    checkpoint, _ = advance(checkpoint, item, action="submit_retelling", value="Пересказ")
    checkpoint, _ = advance(checkpoint, item, action="skip_retelling_addition")
    for _ in item["orientation_questions"]:
        checkpoint, _ = advance(checkpoint, item, action="submit_answer", value="Ответ")
    checkpoint, _ = advance(checkpoint, item, action="submit_image_description", value="Описание")
    checkpoint, _ = advance(checkpoint, item, action="skip_image_description_addition")
    for _ in item["image_questions"]:
        checkpoint, _ = advance(checkpoint, item, action="submit_answer", value="Ответ")
    checkpoint, _ = advance(checkpoint, item, action="request_prompt")
    checkpoint, _ = advance(checkpoint, item, action="request_prompt")
    checkpoint, _ = advance(checkpoint, item, action="submit_answer", value="Ответ")
    assert checkpoint["responses"]["memory"][0]["prompt_level"] == 2
    assert checkpoint["current_prompt_level"] == 0


def test_demo_transcripts_reach_only_the_specialist_report():
    checkpoint = initial_checkpoint("demo-test-01")
    checkpoint["responses"]["retelling"] = "Распознанный пересказ"
    session = {
        "session_id": "situational-1",
        "scenario": "situational_task_demo",
        "status": "completed",
        "started_at": "2026-10-28T10:00:00+00:00",
        "finished_at": "2026-10-28T10:05:00+00:00",
        "checkpoint": checkpoint,
        "result": result_from_checkpoint(checkpoint),
        "events": [],
    }
    report = specialist_report([], sessions=[session])
    assert report["situational_tasks"][0]["responses"]["retelling"] == "Распознанный пересказ"
    assert report["situational_tasks"][0]["has_total_score"] is False


def test_demo_scoring_keeps_independent_metrics_without_a_total():
    item = narrative()
    item["demo_scoring"] = {
        "recall_units": [{"label": "Суп", "all": [["суп"]]}],
        "orientation_rules": [{"all": [["виктор"]]}] * 4,
        "image_concepts": [{"label": "Плита", "all": [["плит"]]}],
        "risk_rule": {"strong": ["пожар"], "basic": ["выкип"]},
        "action_rule": {"full": ["выключить плит"], "partial": ["вернуться"]},
        "memory_rules": [{"all": [["суп"]]}] * 4,
    }
    checkpoint = initial_checkpoint(item["id"])
    checkpoint["responses"] = {
        "retelling": "Он готовил суп",
        "orientation": [{"question_index": i, "answer": "Виктор", "prompt_level": 0} for i in range(4)],
        "image_description": "Плита",
        "image_questions": [
            {"question_index": 0, "answer": "Суп выкипит и начнётся пожар", "prompt_level": 0},
            {"question_index": 1, "answer": "Выключить плиту", "prompt_level": 0},
        ],
        "memory": [{"question_index": i, "answer": "Суп", "prompt_level": 0} for i in range(4)],
    }
    scores = score_demo(checkpoint, item)
    assert scores["risk_understanding"]["score"] == 2
    assert scores["practical_solution"]["score"] == 2
    assert scores["memory_attention"]["score"] == 8
    assert "total_score" not in scores

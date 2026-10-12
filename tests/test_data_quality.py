"""Ограничение интерпретации при низком качестве данных.

ТЗ: «при низком качестве данных — явное ограничение интерпретации», его
видят и пользователь, и специалист. Методология скрининга 2.0, раздел 6.1:
нераспознанные ответы, отметка «низкая достоверность» домена при 2 и более.
"""
from __future__ import annotations

from neuro_mirror.screening.data_quality import LOW_CONFIDENCE_THRESHOLD, assess
from neuro_mirror.screening.report_views import specialist_report, user_view


def task(task_id, domain, *, transcript="ответ", max_score=1):
    return {"task_id": task_id, "domain": domain, "transcript": transcript, "score": 0, "max_score": max_score}


def moca(tasks, **domains):
    return {"report_type": "moca", "domains": {"moca_tasks": tasks, "moca_score": 9, "moca_max_score": 15, **domains},
            "summary": {"limitations": ""}}


CLEAN = moca([task("language_sentence_1", "Речь"), task("abstraction_1", "Абстракция")])
TWO_SILENT = moca([
    task("language_sentence_1", "Речь", transcript=""),
    task("language_sentence_2", "Речь", transcript="  "),
    task("abstraction_1", "Абстракция", transcript=""),
])


def test_a_clean_session_has_no_limitation():
    quality = assess(CLEAN)
    assert quality["limited"] is False
    assert quality["user_text"] == ""
    assert user_view(CLEAN)["quality"] == {"limited": False, "text": ""}


def test_unrecognized_answers_are_counted_by_domain():
    unrecognized = assess(TWO_SILENT)["unrecognized"]
    assert unrecognized["count"] == 3
    assert unrecognized["total"] == 3
    assert unrecognized["by_domain"] == {"Речь": 2, "Абстракция": 1}


def test_two_unrecognized_answers_mark_the_domain_low_confidence():
    assert LOW_CONFIDENCE_THRESHOLD == 2
    quality = assess(TWO_SILENT)
    assert quality["low_confidence_domains"] == ["Речь"]
    assert any("Прослушайте транскрипт" in reason for reason in quality["reasons"])


def test_a_learning_trial_without_score_is_not_an_unrecognized_answer():
    """Проба заучивания баллов не даёт — её молчание не снижает достоверность."""
    report = moca([task("memory_1", "Память", transcript="", max_score=0)])
    assert assess(report)["unrecognized"]["count"] == 0


def test_the_user_is_told_plainly_which_part_may_be_inaccurate():
    text = user_view(TWO_SILENT)["quality"]["text"]
    assert "«Речь»" in text
    assert "может быть неточным" in text
    assert "достоверность" not in text, "без терминов методики"
    assert "специалистом" in text


def test_poor_conditions_and_video_limit_the_result():
    report = moca([task("a", "Речь")], video_quality_issues=["no_face"])
    report["summary"]["limitations"] = "Результат может быть ограничен условиями прохождения: фоновый шум."
    quality = assess(report)
    assert quality["limited"]
    assert any("лицо не было видно" in reason for reason in quality["reasons"])
    assert "фоновый шум" in quality["user_text"]


def test_an_unmeasured_pulse_limits_the_screening_but_a_disabled_one_does_not():
    failed = {"report_type": "screening", "domains": {"heart_rate_bpm": None, "heart_rate_status": "unavailable"}}
    disabled = {"report_type": "screening", "domains": {"heart_rate_bpm": None, "heart_rate_status": "disabled"}}
    assert assess(failed)["limited"]
    assert not assess(disabled)["limited"]


def test_an_incomplete_hads_limits_the_result():
    report = {"report_type": "hads", "domains": {"hads_answered_count": 10, "hads_question_count": 14}}
    assert "10 из 14" in assess(report)["reasons"][0]


def test_the_specialist_sees_the_details():
    quality = specialist_report([TWO_SILENT], sessions=[])["moca"][0]["quality"]
    assert quality["low_confidence_domains"] == ["Речь"]
    assert quality["unrecognized"]["by_domain"]["Речь"] == 2

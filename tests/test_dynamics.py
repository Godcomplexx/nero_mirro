"""Динамика в отчёте специалиста (Методология скрининга 2.0, раздел 8)."""
from __future__ import annotations

from neuro_mirror.screening.dynamics import dynamics
from neuro_mirror.screening.report_views import specialist_report


def moca(session_id, at, score, domains, *, version="1.1.0", limitations=""):
    return {
        "report_type": "moca", "session_id": session_id, "stored_at": at, "scenario_version": version,
        "domains": {
            "moca_score": score, "moca_max_score": 15,
            "moca_domains": [
                {"domain": name, "score": value, "max_score": maximum}
                for name, value, maximum in zip(("Память", "Внимание", "Речь", "Абстракция"), domains, (5, 5, 3, 2))
            ],
            "moca_tasks": [],
        },
        "summary": {"limitations": limitations},
    }


def hads(session_id, at, anxiety, depression):
    return {
        "report_type": "screening", "session_id": session_id, "stored_at": at,
        "domains": {"hads_anxiety_score": anxiety, "hads_depression_score": depression,
                    "hads_answered_count": 14, "hads_question_count": 14},
    }


ENTRY = moca("m1", "2026-10-01T10:00:00+00:00", 9, (3, 3, 2, 1))
EXIT = moca("m2", "2026-11-20T10:00:00+00:00", 11, (4, 4, 2, 1))
HADS_IN = hads("h1", "2026-10-01T09:00:00+00:00", 11, 4)
HADS_OUT = hads("h2", "2026-11-20T09:00:00+00:00", 7, 4)


def test_moca_change_by_total_and_domain():
    result = dynamics([EXIT, ENTRY])["moca"]
    assert result["total_change"] == 2
    assert {row["domain"]: row["change"] for row in result["domains"]} == {
        "Память": 1, "Внимание": 1, "Речь": 0, "Абстракция": 0,
    }
    assert result["comparable"] is True


def test_the_course_entry_test_is_the_baseline():
    """Входной — тест, по которому открыт курс, а не самый ранний."""
    early = moca("m0", "2026-09-01T10:00:00+00:00", 5, (1, 1, 2, 1))
    result = dynamics([early, ENTRY, EXIT], entry_session_id="m1")["moca"]
    assert result["from"]["session_id"] == "m1"
    assert result["total_change"] == 2


def test_hads_change_is_shown_as_context():
    result = dynamics([ENTRY, EXIT, HADS_IN, HADS_OUT])["hads"]
    assert result["anxiety"] == {"from": 11, "to": 7, "change": -4}
    assert result["depression"]["change"] == 0
    assert "контекст" in result["note"]


def test_hads_baseline_is_the_one_before_the_entry_test():
    later = hads("h1b", "2026-10-10T09:00:00+00:00", 9, 4)
    result = dynamics([ENTRY, EXIT, HADS_IN, later, HADS_OUT])["hads"]
    assert result["from"]["session_id"] == "h1"


def test_different_scoring_rules_are_not_comparable():
    newer = moca("m2", "2026-11-20T10:00:00+00:00", 11, (4, 4, 2, 1), version="1.2.0")
    result = dynamics([ENTRY, newer])["moca"]
    assert result["comparable"] is False
    assert "версии правил оценки" in result["comparability_notes"][0]


def test_a_limited_session_is_flagged():
    noisy = moca("m2", "2026-11-20T10:00:00+00:00", 11, (4, 4, 2, 1),
                 limitations="Результат может быть ограничен условиями прохождения: фоновый шум.")
    assert dynamics([ENTRY, noisy])["moca"]["comparable"] is False


def test_one_test_gives_no_dynamics():
    result = dynamics([ENTRY, HADS_IN])
    assert result["moca"] is None and result["hads"] is None
    assert "описательная" in result["note"]


def test_the_specialist_report_carries_the_dynamics():
    course = {"entry": {"session_id": "m1"}, "sessions": [], "plan": {}}
    report = specialist_report([EXIT, ENTRY, HADS_IN, HADS_OUT], sessions=[], course=course)
    assert report["dynamics"]["moca"]["total_change"] == 2
    assert report["dynamics"]["hads"]["anxiety"]["change"] == -4


def test_without_a_test_after_the_course_entry_the_previous_one_is_the_baseline():
    """Курс открыт по последнему тесту: сравниваем с тестом перед ним."""
    early = moca("m0", "2026-09-01T10:00:00+00:00", 7, (2, 2, 2, 1))
    result = dynamics([early, ENTRY], entry_session_id="m1")["moca"]
    assert result["from"]["session_id"] == "m0"
    assert result["total_change"] == 2

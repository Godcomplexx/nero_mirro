"""Что из сохранённых результатов видит пользователь и что — специалист.

ТЗ, модуль отчётности и аналитики:

* краткий пользовательский отчёт понятным языком — выполнено, общая оценка
  и динамика в безопасных формулировках, ограничения, рекомендации;
* расширенный отчёт специалиста — баллы, домены, маркеры, качество данных,
  журнал событий, результаты HADS, результаты тренировок;
* разграничение видимости, в том числе правило не показывать пользователю
  балл и интерпретацию HADS (модуль HADS: «балл и клиническая интерпретация
  на пользовательский экран не выводятся»).

Пользовательский вид задан списком разрешённых полей, а не списком
запрещённых: новое поле отчёта по умолчанию остаётся у специалиста и не
попадает к пользователю случайно.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from neuro_mirror.screening.course_report import (
    TRAINING_NOTE,
    course_summary,
    moca_analogs,
    notifications,
    session_report,
)
from neuro_mirror.screening.data_quality import assess
from neuro_mirror.screening.dynamics import dynamics

# Поля записи, которые видит пользователь.
USER_FIELDS = frozenset({
    "report_type", "type", "state", "session_id", "user_id", "stored_at",
    "app_version", "scenario_version", "moment",
})

# Поля «domains», которые видит пользователь. Балл MoCA и профиль по доменам —
# общая оценка и динамика; пульс — результат видеоанализа. О HADS пользователь
# узнаёт только, что опросник заполнен.
USER_DOMAINS = frozenset({
    "moca_score", "moca_max_score", "moca_domains", "moca_training_plan",
    "heart_rate_bpm", "heart_rate_status",
    "hads_answered_count", "hads_question_count",
})

# Поля «summary», которые видит пользователь. Ограничение интерпретации
# приходит отдельно, в «quality» (screening/data_quality.py).
USER_SUMMARY: frozenset[str] = frozenset()

# Рекомендация в пользовательском отчёте — постоянная и безопасная.
USER_RECOMMENDATION = (
    "Результаты — скрининговая информация, они не являются диагнозом и не "
    "заменяют консультацию врача. Подробный отчёт доступен специалисту."
)

# Пометка к речевым показателям (Методология скрининга 2.0).
SPEECH_RESEARCH_NOTE = "Исследовательский показатель, не для клинической интерпретации."

# Типы записей, которые видит пользователь. Ответы опроса самочувствия и
# результаты отдельных игр — материал отчёта специалиста.
USER_REPORT_TYPES = frozenset({"screening", "hads", "moca"})


def user_view(item: dict[str, Any]) -> dict[str, Any]:
    """Запись результата в том виде, в каком её видит пользователь."""
    view = {key: deepcopy(value) for key, value in item.items() if key in USER_FIELDS}
    domains = item.get("domains") or {}
    view["domains"] = {
        key: deepcopy(value) for key, value in domains.items() if key in USER_DOMAINS
    }
    summary = item.get("summary") or {}
    view["summary"] = {
        key: deepcopy(value) for key, value in summary.items() if key in USER_SUMMARY
    }
    # ТЗ: при низком качестве данных — явное ограничение интерпретации,
    # показанное и пользователю. Ему — понятная фраза, без подробностей.
    quality = assess(item)
    view["quality"] = {"limited": quality["limited"], "text": quality["user_text"]}
    return view


def user_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [user_view(item) for item in items if item.get("report_type") in USER_REPORT_TYPES]


# ---- Расширенный отчёт специалиста ----


def _moca_entry(item: dict[str, Any]) -> dict[str, Any]:
    domains = item.get("domains") or {}
    summary = item.get("summary") or {}
    tasks = []
    for task in domains.get("moca_tasks") or []:
        tasks.append({
            "task_id": task.get("task_id"),
            "domain": task.get("domain"),
            "score": task.get("score"),
            "max_score": task.get("max_score"),
            "status": task.get("status"),
            "transcript": task.get("transcript"),
            "expected": task.get("expected"),
            "details": task.get("details"),
        })
    return {
        "session_id": item.get("session_id"),
        "stored_at": item.get("stored_at"),
        "score": domains.get("moca_score"),
        "max_score": domains.get("moca_max_score"),
        "interpretation": summary.get("moca_interpretation", ""),
        "notes": summary.get("moca_notes", ""),
        "domains": deepcopy(domains.get("moca_domains") or []),
        "tasks": tasks,
        "speech_markers": {
            "note": SPEECH_RESEARCH_NOTE,
            "values": deepcopy(domains.get("moca_speech_summary") or {}),
        },
        "quality": {
            **assess(item),
            "video_quality_issues": deepcopy(domains.get("video_quality_issues") or []),
            "session_conditions": deepcopy(item.get("session_conditions") or {}),
        },
        "heart_rate_bpm": domains.get("heart_rate_bpm"),
        "heart_rate_status": domains.get("heart_rate_status"),
        "versions": {
            "app": item.get("app_version"),
            "scenario": item.get("scenario_version"),
        },
    }


def _hads_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    domains = item.get("domains") or {}
    if domains.get("hads_anxiety_score") is None and domains.get("hads_depression_score") is None:
        return None
    summary = item.get("summary") or {}
    hads = ((item.get("sources") or {}).get("hads")) or {}
    return {
        "session_id": item.get("session_id"),
        "stored_at": item.get("stored_at"),
        "report_type": item.get("report_type"),
        "anxiety": {
            "score": domains.get("hads_anxiety_score"),
            "max_score": domains.get("hads_anxiety_max"),
            "interpretation": summary.get("hads_anxiety_interpretation", ""),
        },
        "depression": {
            "score": domains.get("hads_depression_score"),
            "max_score": domains.get("hads_depression_max"),
            "interpretation": summary.get("hads_depression_interpretation", ""),
        },
        "notes": summary.get("hads_notes", ""),
        "answered_count": domains.get("hads_answered_count"),
        "question_count": domains.get("hads_question_count"),
        "answers": [
            {
                "question": answer.get("question"),
                "part": answer.get("part"),
                "option_text": answer.get("option_text"),
                "score": answer.get("score"),
            }
            for answer in hads.get("answers") or []
        ],
        "limitations": summary.get("limitations", ""),
        "quality": assess(item),
    }


def _screening_entry(item: dict[str, Any]) -> dict[str, Any]:
    domains = item.get("domains") or {}
    return {
        "session_id": item.get("session_id"),
        "stored_at": item.get("stored_at"),
        "heart_rate_bpm": domains.get("heart_rate_bpm"),
        "heart_rate_status": domains.get("heart_rate_status"),
        "heart_rate_algorithm": domains.get("heart_rate_algorithm"),
        "video_usable": domains.get("video_usable"),
        "video_quality_issues": deepcopy(domains.get("video_quality_issues") or []),
        "session_conditions": deepcopy(item.get("session_conditions") or {}),
        "limitations": (item.get("summary") or {}).get("limitations", ""),
        "quality": assess(item),
    }


def _san_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": item.get("session_id"),
        "stored_at": item.get("stored_at"),
        "moment": item.get("moment"),
        "complete": item.get("complete"),
        "score": item.get("score"),
        "max_score": item.get("max_score"),
        "groups": deepcopy(item.get("groups") or []),
    }


def _training_entry(
    course: dict[str, Any] | None,
    levels: dict[str, Any],
    log: list[dict[str, Any]],
    san: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if course is None:
        return None
    sessions = []
    for session in course.get("sessions") or []:
        games = session.get("games") or []
        planned = session.get("status") == "planned"
        sessions.append({
            "number": session.get("number"),
            "stage": session.get("stage"),
            "status": session.get("status"),
            "opened_at": session.get("opened_at"),
            "finished_at": session.get("finished_at"),
            "end_reason": session.get("end_reason"),
            "done": sum(1 for game in games if game.get("status") == "done"),
            "total": len(games),
            "pauses": len(session.get("pauses") or []),
            "games": [
                {
                    "position": game.get("position"),
                    "game_code": game.get("game_code"),
                    "title": game.get("title"),
                    "domain": game.get("domain"),
                    "difficulty_level": game.get("difficulty_level"),
                    "adaptation": game.get("adaptation"),
                    "stimulus_set": game.get("stimulus_set"),
                    "status": game.get("status"),
                    "success": deepcopy(game.get("success")),
                    "counted": game.get("counted"),
                    "flags": deepcopy(game.get("flags") or []),
                }
                for game in games
            ] if not planned else [],
            # Отчёт о занятии (методика, 8.2)
            "report": None if planned else session_report(session, san or [], str(course.get("course_id") or "")),
        })
    return {
        "course_id": course.get("course_id"),
        "created_at": course.get("created_at"),
        "finished_at": course.get("finished_at"),
        "entry_session_id": (course.get("entry") or {}).get("session_id"),
        "plan": deepcopy(course.get("plan") or {}),
        "sessions": sessions,
        "levels": deepcopy(levels),
        "level_changes": deepcopy(log),
        "hold": deepcopy(course.get("hold")),
        "red_flags": deepcopy(course.get("red_flags") or []),
        # Отчёт о курсе (методика, 8.3)
        "summary": course_summary(course),
        "note": TRAINING_NOTE,
    }


def _journal(sessions: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows = []
    for session in sessions[:limit]:
        rows.append({
            "session_id": session.get("session_id"),
            "scenario": session.get("scenario"),
            "status": session.get("status"),
            "started_at": session.get("started_at"),
            "finished_at": session.get("finished_at"),
            "interruption_reason": session.get("interruption_reason", ""),
            "events": [
                {"timestamp": event.get("timestamp"), "type": event.get("type"), "details": deepcopy(event.get("details") or {})}
                for event in session.get("events") or []
            ],
        })
    return rows


def specialist_report(
    items: list[dict[str, Any]],
    *,
    sessions: list[dict[str, Any]],
    course: dict[str, Any] | None = None,
    levels: dict[str, Any] | None = None,
    level_changes: list[dict[str, Any]] | None = None,
    journal_limit: int = 50,
) -> dict[str, Any]:
    """Расширенный отчёт специалиста по всем сохранённым результатам.

    ``items`` — записи хранилища одного пользователя, новые сверху;
    ``sessions`` — записи сессий с журналом событий, новые сверху.
    """
    moca = [_moca_entry(item) for item in items if item.get("report_type") == "moca"]
    hads = [
        entry for entry in (
            _hads_entry(item) for item in items if item.get("report_type") in ("hads", "screening")
        ) if entry is not None
    ]
    screening = [_screening_entry(item) for item in items if item.get("report_type") == "screening"]
    san = [_san_entry(item) for item in items if item.get("report_type") == "san_survey"]
    return {
        "moca": moca,
        "hads": hads,
        "screening": screening,
        "san": san,
        "training": _training_entry(course, levels or {}, level_changes or [], san),
        "journal": _journal(sessions, journal_limit),
        # Уведомления по курсу (методика курса, раздел 9)
        "notifications": notifications(course, levels or {}),
        # Раздел 8 методологии: разница MoCA и контекст HADS; оговорка об
        # эффекте научения по формам-аналогам аудио-MoCA (методика курса, 8.3)
        "dynamics": dynamics(
            items,
            entry_session_id=((course or {}).get("entry") or {}).get("session_id"),
            moca_analogs=moca_analogs(course) if course else None,
        ),
        "speech_note": SPEECH_RESEARCH_NOTE,
    }

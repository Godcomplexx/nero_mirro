"""Какой сценарий предложить пользователю следующим.

ТЗ 5.4.8 (модуль-агрегатор) и ПМИ, проверки 1.30 и 1.31: новому
пользователю система предлагает первичное обследование — базовый скрининг,
затем аудио-MoCA; пользователю с завершённым обследованием — тренировки.
Определённый сценарий показывается до начала выполнения, а отчёты доступны
независимо от него.

Решение принимает ядро по сохранённому прогрессу профиля и состоянию курса,
интерфейс только показывает его и открывает нужный раздел.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Раздел интерфейса, который открывает кнопка (id разделов в js/shell.js).
SECTION_SCREENING = "screening"
SECTION_MOCA = "moca"
SECTION_TRAINING = "training"

REPORTS_NOTE = "Отчёты и история результатов доступны в любой момент в разделе «Отчёты»."


def _moment(value: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def next_step(
    progress: dict[str, Any],
    *,
    course: dict[str, Any] | None = None,
    completed_sessions: int = 0,
    sessions_total: int = 12,
) -> dict[str, Any]:
    """Следующий сценарий: что, зачем и какой раздел открыть.

    ``course`` — последний курс пользователя (или None), ``completed_sessions``
    — сколько его занятий уже закрыто.
    """
    # Красный флаг приостановил курс до решения специалиста («Методика
    # подбора и оценки тренировочного курса», раздел 9)
    if course is not None and course.get("hold"):
        return {
            "step": "hold",
            "section": SECTION_TRAINING,
            "title": "Тренировки приостановлены",
            "text": (
                "Обратитесь, пожалуйста, к врачу. Продолжить курс можно после "
                "того, как специалист снимет приостановку."
            ),
            "action": "Открыть тренировку",
            "reports_note": REPORTS_NOTE,
        }

    if not progress.get("screening_done"):
        return {
            "step": "screening",
            "section": SECTION_SCREENING,
            "title": "Первичное обследование",
            "text": (
                "Начните с базового скрининга: проверка камеры и микрофона, "
                "видеоанализ и опросник. Затем пройдите когнитивный тест."
            ),
            "action": "Начать базовый скрининг",
            "reports_note": REPORTS_NOTE,
        }
    if not progress.get("moca_done"):
        return {
            "step": "moca",
            "section": SECTION_MOCA,
            "title": "Первичное обследование: когнитивный тест",
            "text": "Базовый скрининг пройден. Следующий шаг — когнитивный тест: по нему составляется курс тренировок.",
            "action": "Перейти к когнитивному тесту",
            "reports_note": REPORTS_NOTE,
        }

    finished_at = _moment(course.get("finished_at")) if course else None
    tested_at = _moment(progress.get("last_moca_at"))
    if finished_at is not None and (tested_at is None or tested_at <= finished_at):
        return {
            "step": "exit_screening",
            "section": SECTION_MOCA,
            "title": "Повторное обследование",
            "text": (
                f"Курс из {sessions_total} занятий пройден. Пройдите когнитивный тест "
                "ещё раз — по нему будет видна динамика и составлен новый курс."
            ),
            "action": "Перейти к когнитивному тесту",
            "reports_note": REPORTS_NOTE,
        }

    if course is None or finished_at is not None:
        text = "Обследование завершено. По его результатам составлен курс тренировок."
        action = "Начать тренировку"
    else:
        number = min(completed_sessions + 1, sessions_total)
        text = f"Продолжите курс тренировок: занятие {number} из {sessions_total}."
        action = "Продолжить тренировку" if completed_sessions else "Начать тренировку"
    return {
        "step": "training",
        "section": SECTION_TRAINING,
        "title": "Курс тренировок",
        "text": text,
        "action": action,
        "reports_note": REPORTS_NOTE,
    }

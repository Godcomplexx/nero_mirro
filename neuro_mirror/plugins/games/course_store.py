"""Хранение курса тренировок: 12 занятий, их планы и исходы заданий.

Курс создаётся сразу целиком: 12 слотов с одними и теми же заданиями. Слот
ждёт в статусе ``planned``; когда занятие открывается, в него проставляются
уровни форм по итогам предыдущих занятий, и дальше план не пересобирается:
перезагрузка страницы или возврат к прерванному занятию берут сохранённый
план («Методика подбора и оценки тренировочного курса» v2, раздел 4.4). Исход
каждого задания дописывается к его строке плана.

Статусы задания:

* ``pending`` — ещё не начиналось;
* ``started`` — начато, исхода нет;
* ``done`` — игра закончилась и прислала исход;
* ``abandoned`` — начато и брошено: пользователь завершил занятие или перешёл
  к другому заданию. Нулём не считается и в адаптацию не входит (6.2);
* ``not_presented`` — занятие закончилось раньше, чем задание показали.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neuro_mirror.plugins.games.catalog import get_game_definition
from neuro_mirror.screening.difficulty_policy import FormState, Success
from neuro_mirror.screening.training_course import (
    COURSE_SESSIONS,
    CoursePass,
    apply_levels,
    course_slots,
)

SESSION_PLANNED = "planned"
SESSION_IN_PROGRESS = "in_progress"
SESSION_COMPLETED = "completed"
SESSION_INCOMPLETE = "incomplete"

ITEM_PENDING = "pending"
ITEM_STARTED = "started"
ITEM_DONE = "done"
ITEM_ABANDONED = "abandoned"
ITEM_NOT_PRESENTED = "not_presented"


class CourseError(LookupError):
    """Запрос не подходит к текущему состоянию курса."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TrainingCourseStore:
    def __init__(self, path: str | Path = "runtime/deidentified/training_courses.json") -> None:
        self.path = Path(path)
        self._courses = self._load()

    # ---- Чтение ----

    def latest_course(self, user_id: str) -> dict[str, Any] | None:
        # Курс без общего состава («plan») записан первой версией, где формы
        # подбирались заново к каждому занятию. Он остаётся в файле, но не
        # продолжается: вместо него открывается курс из 12 слотов.
        courses = [
            item for item in self._courses
            if item.get("user_id") == user_id and "plan" in item
        ]
        return courses[-1] if courses else None

    def open_session(self, user_id: str) -> dict[str, Any] | None:
        course = self.latest_course(user_id)
        if course is None:
            return None
        for session in course["sessions"]:
            if session.get("status") == SESSION_IN_PROGRESS:
                return session
        return None

    @staticmethod
    def closed_sessions(course: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            item for item in course["sessions"]
            if item.get("status") in (SESSION_COMPLETED, SESSION_INCOMPLETE)
        ]

    @staticmethod
    def next_slot(course: dict[str, Any]) -> dict[str, Any] | None:
        return next((item for item in course["sessions"] if item.get("status") == SESSION_PLANNED), None)

    @staticmethod
    def is_finished(course: dict[str, Any]) -> bool:
        return len(TrainingCourseStore.closed_sessions(course)) >= COURSE_SESSIONS

    @staticmethod
    def passes(course: dict[str, Any]) -> list[CoursePass]:
        """Прохождения курса в порядке показа — основа уровней форм."""
        result: list[CoursePass] = []
        for session in course["sessions"]:
            for item in sorted(session["games"], key=lambda row: row["position"]):
                if item.get("status") != ITEM_DONE:
                    continue
                counted = item.get("success") if item.get("counted") else None
                result.append(
                    CoursePass(
                        session_number=int(session["number"]),
                        game_code=str(item["game_code"]),
                        result=Success(**counted) if counted else None,
                    )
                )
        return result

    # ---- Изменения ----

    def create_course(
        self,
        *,
        user_id: str,
        entry_session_id: str,
        profile: list[dict[str, Any]],
        composition: dict[str, Any],
    ) -> dict[str, Any]:
        """Новый курс сразу на 12 занятий.

        Недобор фиксируется по входному скринингу на весь курс, а с ним и
        состав: ``composition`` — план по доменам и задания по порядку.
        """
        sessions = []
        for slot in course_slots(composition["games"], user_id):
            for item in slot["games"]:
                item.update(status=ITEM_PENDING, attempts=0, game_session_id=None)
            sessions.append({
                **slot,
                "status": SESSION_PLANNED,
                "opened_at": None,
                "finished_at": None,
                "end_reason": None,
                "level_changes": [],
                "pauses": [],
            })
        course = {
            "course_id": uuid.uuid4().hex,
            "user_id": user_id,
            "created_at": _now(),
            "finished_at": None,
            "entry": {"session_id": entry_session_id, "profile": list(profile)},
            "plan": dict(composition["plan"]),
            "skipped": list(composition.get("skipped") or []),
            "sessions": sessions,
        }
        self._courses.append(course)
        self._save()
        return course

    def open_slot(
        self,
        course: dict[str, Any],
        slot: dict[str, Any],
        *,
        states: dict[str, FormState],
        level_changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Открыть занятие: проставить уровни форм и зафиксировать план."""
        apply_levels(slot["games"], states)
        slot.update(status=SESSION_IN_PROGRESS, opened_at=_now(), level_changes=list(level_changes))
        self._save()
        return slot

    def begin_item(
        self,
        *,
        user_id: str,
        session_number: int,
        position: int,
        game_code: str,
    ) -> dict[str, Any]:
        """Задание, которое сейчас начинается, — со всем, что нужно игре.

        Начатое и брошенное перед этим задание получает статус ``abandoned``.
        Повторный старт того же задания (после перезагрузки или паузы) не
        считается прерыванием: прерванная проба не оценивается и проходится
        заново.
        """
        session = self.open_session(user_id)
        if session is None or int(session["number"]) != int(session_number):
            raise CourseError("Это занятие уже завершено. Откройте тренировку заново.")
        item = next((row for row in session["games"] if int(row["position"]) == int(position)), None)
        code = get_game_definition(game_code).code
        if item is None or item["game_code"] != code:
            raise CourseError("Такого задания в занятии нет.")
        if item["status"] in (ITEM_DONE, ITEM_ABANDONED):
            raise CourseError("Это задание занятия уже пройдено.")
        for other in session["games"]:
            if other is not item and other["status"] == ITEM_STARTED:
                other["status"] = ITEM_ABANDONED
                other["finished_at"] = _now()
        item["status"] = ITEM_STARTED
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item.setdefault("started_at", _now())
        self._save()
        return item

    def attach_game_session(self, *, user_id: str, session_number: int, position: int, game_session_id: str) -> None:
        session = self.open_session(user_id)
        if session is None or int(session["number"]) != int(session_number):
            return
        for item in session["games"]:
            if int(item["position"]) == int(position):
                item["game_session_id"] = game_session_id
                self._save()
                return

    def record_outcome(
        self,
        *,
        game_session_id: str,
        completion_status: str,
        technical_validity: str,
        success: Success | None,
        counted: bool,
        metrics: dict[str, Any],
    ) -> bool:
        """Дописать исход задания. Возвращает, относилась ли игра к курсу."""
        for course in reversed(self._courses):
            for session in course["sessions"]:
                if session.get("status") != SESSION_IN_PROGRESS:
                    continue
                for item in session["games"]:
                    if item.get("game_session_id") != game_session_id:
                        continue
                    if item["status"] != ITEM_STARTED:
                        return True
                    item.update(
                        status=ITEM_DONE,
                        finished_at=_now(),
                        completion_status=completion_status,
                        technical_validity=technical_validity,
                        success=success.to_dict() if success else None,
                        counted=counted,
                        metrics=dict(metrics),
                    )
                    if all(row["status"] == ITEM_DONE for row in session["games"]):
                        self._close(course, session, SESSION_COMPLETED, reason="все задания выполнены")
                    self._save()
                    return True
        return False

    def finish_session(self, user_id: str, *, reason: str) -> dict[str, Any] | None:
        """Завершить открытое занятие, в том числе досрочно (4.5, п. 6)."""
        course = self.latest_course(user_id)
        session = self.open_session(user_id)
        if course is None or session is None:
            return None
        complete = all(row["status"] == ITEM_DONE for row in session["games"])
        self._close(course, session, SESSION_COMPLETED if complete else SESSION_INCOMPLETE, reason=reason)
        self._save()
        return session

    def pause(self, user_id: str, *, position: int | None) -> dict[str, Any]:
        session = self.open_session(user_id)
        if session is None:
            raise CourseError("Открытого занятия нет.")
        pauses = session["pauses"]
        if pauses and pauses[-1].get("ended_at") is None:
            return pauses[-1]
        record = {"position": position, "paused_at": _now(), "ended_at": None, "ended_by": None}
        pauses.append(record)
        self._save()
        return record

    def resume(self, user_id: str) -> dict[str, Any] | None:
        session = self.open_session(user_id)
        if session is None:
            return None
        record = self._end_pause(session, "продолжение")
        self._save()
        return record

    # ---- Служебное ----

    def _close(self, course: dict[str, Any], session: dict[str, Any], status: str, *, reason: str) -> None:
        moment = _now()
        self._end_pause(session, "завершение занятия")
        for item in session["games"]:
            if item["status"] == ITEM_STARTED:
                item["status"] = ITEM_ABANDONED
                item["finished_at"] = moment
            elif item["status"] == ITEM_PENDING:
                item["status"] = ITEM_NOT_PRESENTED
        session.update(status=status, finished_at=moment, end_reason=reason)
        if self.is_finished(course):
            course["finished_at"] = moment

    @staticmethod
    def _end_pause(session: dict[str, Any], ended_by: str) -> dict[str, Any] | None:
        pauses = session.get("pauses") or []
        if not pauses or pauses[-1].get("ended_at") is not None:
            return None
        pauses[-1].update(ended_at=_now(), ended_by=ended_by)
        return pauses[-1]

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [dict(item) for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(self._courses, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

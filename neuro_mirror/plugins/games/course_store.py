"""Хранение курса тренировок: 12 занятий, их планы и исходы заданий.

Курс создаётся сразу целиком: 12 слотов и состав по доменам. Слот ждёт в
статусе ``planned``; когда занятие открывается, в него записываются
подобранные формы, их уровни по итогам предыдущих занятий и стимульные
наборы, и дальше план не пересобирается:
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

У брошенного задания записывается причина (6.3): код и подпись из
``training_safety``. Облегчённая альтернатива прерванного задания (6.3)
встаёт в план сразу за ним: у неё ``alternative_for`` — номер прерванного
задания, а у прерванного ``replaced_by`` — номер альтернативы. Уровень
альтернативы временный: её прохождение в адаптацию не входит.

Красный флаг (раздел 9) приостанавливает курс (``hold``): новое занятие не
открывается, пока специалист не снимет приостановку.
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
    slot_items,
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

    @staticmethod
    def is_alternative(item: dict[str, Any]) -> bool:
        return item.get("alternative_for") is not None

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
            for item in session["games"]:
                # Облегчённая альтернатива идёт на временном уровне и в
                # адаптацию не входит (6.3)
                if item.get("status") != ITEM_DONE or TrainingCourseStore.is_alternative(item):
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
        plan: dict[str, int],
    ) -> dict[str, Any]:
        """Новый курс сразу на 12 занятий.

        Недобор фиксируется по входному скринингу на весь курс, а с ним и
        состав по доменам — ``plan``. Формы подбираются при открытии занятий.
        """
        sessions = [
            {
                **slot,
                "status": SESSION_PLANNED,
                "opened_at": None,
                "finished_at": None,
                "end_reason": None,
                "skipped": [],
                "level_changes": [],
                "pauses": [],
            }
            for slot in course_slots()
        ]
        course = {
            "course_id": uuid.uuid4().hex,
            "user_id": user_id,
            "created_at": _now(),
            "finished_at": None,
            "entry": {"session_id": entry_session_id, "profile": list(profile)},
            "plan": dict(plan),
            "sessions": sessions,
            "red_flags": [],
            "hold": None,
        }
        self._courses.append(course)
        self._save()
        return course

    def open_slot(
        self,
        course: dict[str, Any],
        slot: dict[str, Any],
        *,
        games: list[dict[str, Any]],
        states: dict[str, FormState],
        level_changes: list[dict[str, Any]],
        skipped: list[dict[str, str]] | None = None,
        order: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Открыть занятие: записать подобранные формы с уровнями и наборами.

        ``games`` — формы по порядку (``training_session``). После этого план
        занятия не меняется.
        """
        course_user = str(course.get("user_id") or "")
        items = slot_items(games, course_user, int(slot["number"]))
        apply_levels(items, states)
        for item in items:
            item.update(status=ITEM_PENDING, attempts=0, game_session_id=None)
        slot.update(
            games=items,
            skipped=list(skipped or []),
            status=SESSION_IN_PROGRESS,
            opened_at=_now(),
            level_changes=list(level_changes),
            # Порядок заданий: зерно, нарушения желательных правил,
            # закреплённые первое и последнее задания (4.4)
            order=order,
        )
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

    def resume_item(self, *, user_id: str, session_number: int, position: int, game_session_id: str) -> dict[str, Any]:
        """Задание, которое продолжается после паузы с прерванной пробы (4.5, п. 5).

        Продолжается только начатое задание этого занятия с той же игровой
        сессией; попыткой оно не считается.
        """
        session = self.open_session(user_id)
        if session is None or int(session["number"]) != int(session_number):
            raise CourseError("Это занятие уже завершено. Откройте тренировку заново.")
        item = self._item(session, position)
        if item is None or item["status"] != ITEM_STARTED or item.get("game_session_id") != game_session_id:
            raise CourseError("Это задание не продолжить с места паузы.")
        item["resumed"] = int(item.get("resumed") or 0) + 1
        self._save()
        return item

    def interrupt_item(self, user_id: str, *, position: int, reason: dict[str, Any]) -> dict[str, Any]:
        """Прервать задание с записанной причиной (6.3, п. 1).

        Задание получает статус ``abandoned``: нулём оно не считается и в
        адаптацию не входит.
        """
        session = self.open_session(user_id)
        if session is None:
            raise CourseError("Открытого занятия нет.")
        item = self._item(session, position)
        if item is None or item["status"] in (ITEM_DONE, ITEM_ABANDONED, ITEM_NOT_PRESENTED):
            raise CourseError("Это задание уже закончено.")
        item.update(status=ITEM_ABANDONED, finished_at=_now(), interruption_reason=dict(reason))
        self._end_pause(session, "прерывание задания")
        self._save()
        return item

    def add_alternative(self, user_id: str, *, position: int, alternative: dict[str, Any]) -> dict[str, Any]:
        """Поставить облегчённую альтернативу сразу за прерванным заданием (6.3, п. 3)."""
        session = self.open_session(user_id)
        if session is None:
            raise CourseError("Открытого занятия нет.")
        original = self._item(session, position)
        if original is None or original["status"] != ITEM_ABANDONED:
            raise CourseError("Альтернатива ставится только вместо прерванного задания.")
        number = max(int(row["position"]) for row in session["games"]) + 1
        item = {
            **alternative,
            "position": number,
            "alternative_for": int(position),
            "status": ITEM_PENDING,
            "attempts": 0,
            "game_session_id": None,
        }
        original["replaced_by"] = number
        index = session["games"].index(original)
        session["games"].insert(index + 1, item)
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
        u06_status: str | None = None,
        end_reason: str | None = None,
        time_limit_ms: float | None = None,
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
                        u06_status=u06_status,
                        end_reason=end_reason,
                        time_limit_ms=time_limit_ms,
                        success=success.to_dict() if success else None,
                        counted=counted and not self.is_alternative(item),
                        metrics=dict(metrics),
                    )
                    if self._all_settled(session):
                        self._close(course, session, SESSION_COMPLETED, reason="все задания выполнены")
                    self._save()
                    return True
        return False

    def finish_session(
        self, user_id: str, *, reason: str, interruption: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Завершить открытое занятие, в том числе досрочно (4.5, п. 6).

        ``interruption`` — причина прерывания (6.3): она записывается
        заданию, брошенному при завершении.
        """
        course = self.latest_course(user_id)
        session = self.open_session(user_id)
        if course is None or session is None:
            return None
        complete = self._all_settled(session)
        if interruption:
            session["interruption"] = dict(interruption)
        self._close(
            course,
            session,
            SESSION_COMPLETED if complete else SESSION_INCOMPLETE,
            reason=reason,
            interruption=interruption,
        )
        self._save()
        return session

    def pause(self, user_id: str, *, position: int | None, trial: int | None = None) -> dict[str, Any]:
        """Отметить паузу: в каком задании и на какой пробе (4.5, п. 8)."""
        session = self.open_session(user_id)
        if session is None:
            raise CourseError("Открытого занятия нет.")
        pauses = session["pauses"]
        if pauses and pauses[-1].get("ended_at") is None:
            return pauses[-1]
        record = {
            "position": position,
            "trial": trial,
            "paused_at": _now(),
            "ended_at": None,
            "ended_by": None,
        }
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

    # ---- Красные флаги (раздел 9) ----

    def note_pre_check(self, user_id: str, *, new_symptoms: bool) -> dict[str, Any]:
        """Ответ на вопрос о новых симптомах перед занятием."""
        session = self.open_session(user_id)
        if session is None:
            raise CourseError("Открытого занятия нет.")
        session["pre_check"] = {"at": _now(), "new_symptoms": bool(new_symptoms)}
        self._save()
        return session["pre_check"]

    def raise_red_flag(self, user_id: str, *, source: str, detail: str) -> dict[str, Any]:
        """Красный флаг: курс приостанавливается до решения специалиста."""
        course = self.latest_course(user_id)
        if course is None:
            raise CourseError("Курса нет.")
        session = self.open_session(user_id)
        record = {
            "at": _now(),
            "source": source,
            "detail": detail,
            "session_number": int(session["number"]) if session else None,
        }
        course.setdefault("red_flags", []).append(record)
        course["hold"] = {"since": record["at"], "reason": detail, "released_at": None}
        self._save()
        return record

    def release_hold(self, user_id: str, *, note: str = "") -> dict[str, Any] | None:
        """Специалист снимает приостановку курса."""
        course = self.latest_course(user_id)
        if course is None or not course.get("hold"):
            return None
        hold = course["hold"]
        course.setdefault("holds", []).append({**hold, "released_at": _now(), "note": note})
        course["hold"] = None
        self._save()
        return course["holds"][-1]

    # ---- Служебное ----

    @staticmethod
    def _item(session: dict[str, Any], position: int) -> dict[str, Any] | None:
        return next((row for row in session["games"] if int(row["position"]) == int(position)), None)

    @staticmethod
    def _all_settled(session: dict[str, Any]) -> bool:
        """Все задания выполнены; прерванное, заменённое выполненной
        альтернативой, тоже считается закрытым."""
        by_position = {int(row["position"]): row for row in session["games"]}
        for item in session["games"]:
            if item["status"] == ITEM_DONE:
                continue
            replacement = by_position.get(int(item.get("replaced_by") or 0))
            if item["status"] == ITEM_ABANDONED and replacement and replacement["status"] == ITEM_DONE:
                continue
            return False
        return True

    def _close(
        self,
        course: dict[str, Any],
        session: dict[str, Any],
        status: str,
        *,
        reason: str,
        interruption: dict[str, Any] | None = None,
    ) -> None:
        moment = _now()
        self._end_pause(session, "завершение занятия")
        for item in session["games"]:
            if item["status"] == ITEM_STARTED:
                item["status"] = ITEM_ABANDONED
                item["finished_at"] = moment
                if interruption:
                    item["interruption_reason"] = dict(interruption)
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

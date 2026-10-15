"""Base request/reply protocol for newly implemented browser games.

Кроме старта и ответа каркас знает три служебных действия ответа
(``action``), одинаковых для всех игр («Методика подбора и оценки
тренировочного курса» v2):

* ``pause`` — задание поставлено на паузу; ядро запоминает момент, чтобы
  время паузы не вошло в активное время (4.5, п. 4), и называет пробу, на
  которой нажата пауза (4.5, п. 8);
* ``resume`` — продолжение после паузы: прерванная проба не оценивается и
  предъявляется заново, у форм памяти — с нового предъявления (4.5, п. 5).
  Что такое проба и как её повторить, решает сама игра (``_resume``);
* ``timeout`` — вышел лимит времени задания (``task_clock``); задание
  кончается со статусом timeout (6.2).

Отчёт о прохождении несёт статус завершения U06 по разделу 6.2
(``u06_status``): completed_success, completed_unsuccessful, timeout,
technical_invalid или «не определено». Статус abandoned ставит курс: игра
о прерывании не узнаёт.
"""
from __future__ import annotations

import random
import time
from copy import deepcopy
from typing import Any

from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.catalog import get_game_definition

# Статусы завершения U06 (методика, раздел 6.2)
U06_SUCCESS = "completed_success"
U06_UNSUCCESSFUL = "completed_unsuccessful"
U06_TIMEOUT = "timeout"
U06_TECHNICAL_INVALID = "technical_invalid"
U06_UNDETERMINED = "undetermined"

# Чем кончилось задание: игра пишет это в ответ (``end_reason``)
END_DONE = "done"
END_ATTEMPTS = "attempts"
END_TIMEOUT = "timeout"


def u06_status(metrics: dict[str, Any], end_reason: str) -> str:
    """Статус завершения прохождения по его показателям (6.2).

    Статус рассчитывается, а не подставляется: без показателей полноты и
    пригодности он не определён.
    """
    complete = metrics.get("u06_complete")
    valid = metrics.get("u06_technically_valid")
    if valid is False:
        return U06_TECHNICAL_INVALID
    if complete is None or valid is None:
        return U06_UNDETERMINED
    if end_reason == END_TIMEOUT:
        return U06_TIMEOUT
    if end_reason == END_ATTEMPTS or complete is False:
        return U06_UNSUCCESSFUL
    return U06_SUCCESS


class BrowserGamePlugin(Plugin):
    """Standard transport shell; a game implements only start and answer logic."""

    game_code = ""
    game_definition = None
    start_handler = "_start"
    answer_handler = "_answer"
    _event_list_attributes = ("round_events", "rounds", "trials", "completed_words", "results")

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.definition = self.game_definition or get_game_definition(self.game_code)
        # Когда нажата пауза: по игровой сессии
        self._paused_at_ms: dict[str, float] = {}

    def _session_random(self, payload: dict[str, Any]) -> random.Random:
        """Генератор случайности задания (методика, раздел 6.5).

        У задания курса ядро передаёт зерно «пользователь + форма + номер
        занятия»: перемешивание повторяется при повторном запуске того же
        занятия и различается между занятиями. Без зерна (свободная игра)
        — общий генератор игры.
        """
        seed = payload.get("randomization_seed")
        if isinstance(seed, int) and not isinstance(seed, bool):
            return random.Random(seed)
        return getattr(self, "_random", None) or random.SystemRandom()

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            self.definition.start_request_topic,
            self.definition.answer_request_topic,
        )

    async def handle_event(self, event: Event) -> None:
        request_id = str(event.payload.get("_request_id") or "")
        is_start = event.topic == self.definition.start_request_topic
        result = self.start_game(event.payload) if is_start else self.answer_game(event.payload)
        checkpoint = result.get("checkpoint")
        if isinstance(checkpoint, dict):
            await self.bus.publish(
                Event(topic=Topics.GAME_SESSION_CHECKPOINT, source=self.name, payload=checkpoint)
            )
        if is_start and result.get("ok") and result.get("session_id"):
            await self.bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_STARTED,
                    source=self.name,
                    payload={
                        "game_session_id": str(result["session_id"]),
                        "game_code": self.definition.code,
                        "user_id": str(event.payload.get("user_id") or ""),
                        "stimulus_set": str(
                            event.payload.get("stimulus_set")
                            or (
                                self.definition.stimulus_sets[0]
                                if self.definition.stimulus_sets
                                else ""
                            )
                        ),
                        "difficulty_level": event.payload.get("difficulty_level"),
                    },
                )
            )
        report = result.get("report")
        if isinstance(report, dict):
            await self.bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_COMPLETED,
                    source=self.name,
                    payload=deepcopy(report),
                )
            )
        result["_reply_to"] = request_id
        result.setdefault("game_code", self.definition.code)
        await self.bus.publish(
            Event(
                topic=(
                    self.definition.start_response_topic
                    if is_start
                    else self.definition.answer_response_topic
                ),
                source=self.name,
                payload=result,
            )
        )

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return getattr(self, self.start_handler)()

    def answer_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_session_id = str(payload.get("session_id") or "")
        active_session = getattr(self, "_sessions", {}).get(requested_session_id)
        action = payload.get("action")
        if action == "pause":
            return self._pause_control(requested_session_id, active_session)
        if action == "resume":
            return self._resume_control(requested_session_id, active_session)
        difficulty_parameters = self._difficulty_parameters(active_session)
        if action == "timeout":
            if active_session is None:
                return {"ok": False, "message": "Игровая сессия не найдена."}
            result = self._timeout(active_session)
        else:
            result = getattr(self, self.answer_handler)(payload)
        if not result.get("ok"):
            return result
        if active_session is not None:
            difficulty_level = getattr(active_session, "difficulty_level", None)
            if difficulty_level is not None:
                result.setdefault("difficulty_level", difficulty_level)
            if difficulty_parameters:
                result.setdefault("difficulty_parameters", deepcopy(difficulty_parameters))
        session_id = str(payload.get("session_id") or result.get("session_id") or "")
        events = result.get("events")
        if not isinstance(events, list):
            session = getattr(self, "_sessions", {}).get(session_id)
            events = self._session_events(session)
        journal = [self._normalise_event(index, item) for index, item in enumerate(events or (), start=1)]
        result["checkpoint"] = {
            "source": self.definition.topic_prefix,
            "session_id": session_id,
            "next_index": len(journal),
            "trials": deepcopy(journal),
        }
        if result.get("finished"):
            self._paused_at_ms.pop(session_id, None)
            metrics = result.get("metrics") or {}
            complete = metrics.get("u06_complete")
            technically_valid = metrics.get("u06_technically_valid")
            end_reason = str(result.get("end_reason") or END_DONE)
            result["end_reason"] = end_reason
            result["report"] = {
                "type": "training_game",
                "game_code": self.definition.code,
                "session_id": session_id,
                "difficulty_level": result.get("difficulty_level"),
                "difficulty_parameters": deepcopy(result.get("difficulty_parameters") or {}),
                "end_reason": end_reason,
                "time_limit_ms": result.get("time_limit_ms"),
                "u06_status": u06_status(metrics, end_reason),
                "completion_status": (
                    "completed" if complete is True
                    else "incomplete" if complete is False
                    else "unknown"
                ),
                "technical_validity": (
                    "valid" if technically_valid is True
                    else "invalid" if technically_valid is False
                    else "unknown"
                ),
                "metrics": deepcopy(result.get("metrics") or {}),
                "trials": deepcopy(journal),
            }
        return result

    # ---- Пауза, продолжение и лимит времени ----

    def _pause_control(self, session_id: str, session: Any) -> dict[str, Any]:
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        self._paused_at_ms.setdefault(session_id, time.time() * 1000)
        return {"ok": True, "paused": True, "session_id": session_id, "trial": self._trial_number(session)}

    def _resume_control(self, session_id: str, session: Any) -> dict[str, Any]:
        if session is None:
            # Сессии игры нет (например, ядро перезапускали) — задание
            # начнётся заново обычным стартом.
            return {"ok": False, "resumable": False, "message": "Игровая сессия не найдена."}
        paused_at = self._paused_at_ms.pop(session_id, None)
        paused_ms = max(0.0, time.time() * 1000 - paused_at) if paused_at is not None else 0.0
        result = self._resume(session, paused_ms)
        if result.get("ok"):
            result.update(resumed=True, interrupted_trial=self._trial_number(session))
        return result

    def _resume(self, session: Any, paused_ms: float) -> dict[str, Any]:
        """Предъявить прерванную пробу заново; ответ — как на старт.

        ``paused_ms`` — длительность паузы: её не включают во время задания.
        Игра без своего правила продолжения начинается заново.
        """
        return {"ok": False, "resumable": False, "message": "Задание продолжается только с начала."}

    def _trial_number(self, session: Any) -> int | None:
        """Номер текущей пробы (с 1) — для журнала пауз; у каждой игры свой."""
        return None

    def _timeout(self, session: Any) -> dict[str, Any]:
        """Вышел лимит времени: закончить задание (у игр с лимитом)."""
        return {"ok": False, "message": "У задания нет лимита времени."}

    @staticmethod
    def _difficulty_parameters(session: Any) -> dict[str, Any]:
        """Keep the effective task settings available after a session is removed."""
        if session is None:
            return {}
        explicit = getattr(session, "difficulty_parameters", None)
        if isinstance(explicit, dict):
            return explicit

        parameters: dict[str, Any] = {}
        scalar_fields = {
            "max_rounds": "cycles",
            "missing_items": "missing_items",
            "grid_size": "grid_size",
            "target_count": "tracked_objects",
            "choice_count": "choices",
            "disk_count": "elements",
        }
        for attribute, key in scalar_fields.items():
            value = getattr(session, attribute, None)
            if value is not None:
                parameters[key] = value

        letter_range = getattr(session, "letter_range", None)
        if isinstance(letter_range, tuple) and len(letter_range) == 2:
            parameters.update(
                minimum_letters=letter_range[0], maximum_letters=letter_range[1]
            )
        target_range = getattr(session, "target_range", None)
        if isinstance(target_range, tuple) and len(target_range) == 2:
            parameters.update(
                minimum_targets=target_range[0], maximum_targets=target_range[1]
            )
        puzzles = getattr(session, "puzzles", None)
        if isinstance(puzzles, list) and puzzles:
            parameters["pieces"] = puzzles[0]["rows"] * puzzles[0]["columns"]
        scenes = getattr(session, "scenes", None)
        if isinstance(scenes, list) and scenes:
            parameters["differences"] = len(scenes[0].get("differences", ()))
        return parameters

    def _session_events(self, session: object | None) -> list[dict[str, Any]]:
        if session is None:
            return []
        for attribute in self._event_list_attributes:
            value = getattr(session, attribute, None)
            if isinstance(value, list):
                return value
        return []

    @staticmethod
    def _normalise_event(index: int, raw_event: object) -> dict[str, Any]:
        raw = deepcopy(raw_event) if isinstance(raw_event, dict) else {"value": raw_event}
        answer_keys = {
            key for key in raw
            if key.startswith("selected")
            or key in {
                "answer",
                "assembled",
                "boundary_errors",
                "clicks",
                "invalid_words",
                "path",
                "placements",
                "recognized",
                "repetitions",
                "responded",
                "tokens",
                "transcript",
                "valid_words",
            }
        }
        time_keys = {
            key for key in raw
            if key.endswith("_ms") or key in {"reaction_time", "duration"}
        }
        stimulus = {key: value for key, value in raw.items() if key not in answer_keys | time_keys | {"correct", "valid"}}
        answer = {key: raw[key] for key in answer_keys}
        elapsed = next((raw[key] for key in time_keys if isinstance(raw.get(key), (int, float))), 0.0)
        return {
            "index": index,
            "stimulus": stimulus,
            "answer": answer,
            "elapsed_ms": max(0.0, float(elapsed)),
            "valid": raw.get("valid"),
            "correct": raw.get("correct"),
            "raw": raw,
        }

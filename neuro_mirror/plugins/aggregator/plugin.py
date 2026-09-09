from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.core.settings import Settings
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer
from neuro_mirror.version import session_version_manifest


logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "idle"
    SCREENING = "screening"
    MOCA = "moca"
    HADS = "hads"
    APPEARANCE = "appearance"
    REPORTING = "reporting"


IGNORED_UI_ACTIONS = {
    "start_preview",
    "stop_preview",
    "release_camera",
    "start_voice_capture",
    "stop_voice_capture",
    "moca_tts_finished",
    "hads_tts_finished",
    "hads_answer",  # handled by HadsTestPlugin
    "analyze_appearance",  # handled entirely by the browser via /api/appearance/analyze
    "camera_vision_query",  # handled entirely by the browser via /api/assistant/camera-vision
}


class AggregatorPlugin(ProcessorPlugin):
    plugin_name = "aggregator"

    def __init__(
        self,
        bus,
        *,
        appearance_composer: AppearanceResponseComposer,
        session_store: SessionStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(bus)
        self.appearance_composer = appearance_composer
        self.state = SessionState.IDLE
        self.history_count = 0
        self._latest_results: dict[str, dict[str, Any]] = {}
        self._pending_capture_mode = ""
        # True when the HADS test was launched as part of the basic screening
        # chain (video analysis → anxiety test → combined report)
        self._screening_chain = False
        # Результаты последней проверки условий сессии (ТЗ 6.3.2)
        self._session_conditions: dict[str, Any] = {}
        self.session_store = session_store
        self.settings = settings
        self._active_user_id = ""
        self._active_session_id = ""
        self._session_permissions: dict[str, bool] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.SYSTEM_BOOTSTRAP,
            Topics.UI_ACTION,
            Topics.AI_COMMAND,
            Topics.DEVICE_SELECTION_RESOLVED,
            Topics.DEVICE_VALIDATION_FAILED,
            Topics.ANALYSIS_RESULT,
            Topics.RPPG_RESULT,
            Topics.VOICE_TEST_RESULT,
            Topics.MOCA_TEST_RESULT,
            Topics.HADS_TEST_RESULT,
            Topics.STORAGE_READ_RESULT,
            Topics.USER_SELECTED,
            Topics.SESSION_CHECKPOINT,
            Topics.SESSION_ERROR,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic in {Topics.SESSION_CHECKPOINT, Topics.SESSION_ERROR,
                           Topics.MOCA_TEST_RESULT, Topics.HADS_TEST_RESULT}:
            session_id = event.payload.get("session_id")
            if session_id is not None and session_id != self._active_session_id:
                return
        if event.topic == Topics.SYSTEM_BOOTSTRAP:
            await self._handle_bootstrap()
            return

        if event.topic == Topics.STORAGE_READ_RESULT:
            self.history_count = len(event.payload.get("items", []))
            return

        if event.topic == Topics.USER_SELECTED:
            next_user = str(event.payload.get("user_id") or "")
            if next_user != self._active_user_id and self._active_session_id:
                self.state = SessionState.IDLE
                self._interrupt_session("Выбран другой пользователь.")
                await self.bus.publish(Event(topic=Topics.MOCA_STOP, source=self.name))
                await self.bus.publish(Event(topic=Topics.HADS_STOP, source=self.name))
                self._latest_results.clear()
                self._screening_chain = False
            self._active_user_id = next_user
            return

        if event.topic == Topics.SESSION_CHECKPOINT:
            if self.session_store is not None and self._active_session_id:
                current = self.session_store.get(self._active_session_id) or {}
                merged_checkpoint = {
                    **dict(current.get("checkpoint") or {}),
                    **event.payload,
                }
                self.session_store.checkpoint(self._active_session_id, merged_checkpoint)
            return

        if event.topic == Topics.SESSION_ERROR:
            reason = str(event.payload.get("reason") or "Ошибка выполнения сессии.")
            self._fail_session(reason)
            self.state = SessionState.IDLE
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={"screen": "idle", "message": reason},
                )
            )
            return

        if event.topic in {Topics.UI_ACTION, Topics.AI_COMMAND}:
            was_busy = self.state != SessionState.IDLE
            await self._handle_action(event.payload)
            if event.payload.get("_request_id") and event.payload.get("action") == "resume_session":
                await self.bus.publish(Event(
                    topic="session.resume.reply", source=self.name,
                    payload={"_reply_to": event.payload["_request_id"],
                             "accepted": not was_busy and self.state != SessionState.IDLE
                             and self._active_session_id == event.payload.get("session_id")},
                ))
            return

        if event.topic == Topics.DEVICE_SELECTION_RESOLVED:
            await self._handle_devices_resolved(event.payload)
            return

        if event.topic == Topics.DEVICE_VALIDATION_FAILED:
            await self._handle_device_validation_failed(event.payload)
            return

        if event.topic == Topics.RPPG_RESULT:
            if self.state == SessionState.SCREENING:
                self._latest_results["video"] = event.payload
                if self.session_store is not None and self._active_session_id:
                    self.session_store.checkpoint(
                        self._active_session_id,
                        {
                            "source": "screening_video",
                            "next_index": 0,
                            "video": event.payload,
                        },
                    )
                await self._maybe_finish_screening()
            return

        if event.topic == Topics.ANALYSIS_RESULT:
            if self.state == SessionState.APPEARANCE:
                await self._finish_appearance_analysis(event.payload)
            return

        if event.topic == Topics.VOICE_TEST_RESULT:
            self._latest_results["voice"] = event.payload
            await self._maybe_finish_screening()
            return

        if event.topic == Topics.MOCA_TEST_RESULT:
            self._latest_results["moca"] = event.payload
            await self._finish_moca()
            return

        if event.topic == Topics.HADS_TEST_RESULT:
            self._latest_results["hads"] = event.payload
            await self._finish_hads()

    async def _handle_bootstrap(self) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.STORAGE_READ,
                source=self.name,
                payload={"collection": "screenings"},
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "idle",
                    "message": "Система готова. Ожидаю запуск скрининга или вопрос к ассистенту.",
                },
            )
        )

    async def _handle_action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or payload.get("command") or "")
        if not action:
            return

        if action in IGNORED_UI_ACTIONS:
            return

        if action in {"start_screening", "start_moca", "start_hads", "resume_session"}:
            if self.state != SessionState.IDLE:
                await self.bus.publish(Event(
                    topic=Topics.UI_UPDATE, source=self.name,
                    payload={"message": "Сначала завершите или остановите текущий тест."},
                ))
                return

        # Результаты проверки условий приходят вместе с командой запуска
        conditions = payload.get("session_conditions")
        if action.startswith("start_") and isinstance(conditions, dict):
            self._session_conditions = conditions
        elif action.startswith("start_"):
            self._session_conditions = {}
        if action.startswith("start_"):
            self._session_permissions = {
                "audio": bool(payload.get("audio_allowed", False)),
                "video": bool(payload.get("video_allowed", False)),
            }

        if action == "start_screening":
            if not self._session_permissions.get("video"):
                await self._publish_consent_required("видеоданных")
                return
            await self._start_screening(payload)
            return

        if action == "start_moca":
            if not self._session_permissions.get("audio"):
                await self._publish_consent_required("аудиоданных")
                return
            await self._start_moca_standalone(payload)
            return

        if action == "start_hads":
            await self._start_hads(chain=False, payload=payload)
            return

        if action == "resume_session":
            await self._resume_session(str(payload.get("session_id") or ""), payload)
            return

        if action == "stop_hads":
            await self.bus.publish(Event(topic=Topics.HADS_STOP, source=self.name, payload={}))
            self.state = SessionState.IDLE
            self._screening_chain = False
            self._interrupt_session(str(payload.get("reason") or "Остановлено пользователем."))
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={"screen": "idle", "message": "Тест на тревожность прерван."},
            ))
            return

        if action == "stop_moca":
            await self.bus.publish(Event(topic=Topics.MOCA_STOP, source=self.name, payload={}))
            self.state = SessionState.IDLE
            self._interrupt_session(str(payload.get("reason") or "Остановлено пользователем."))
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={"screen": "idle", "message": "Тест MoCA прерван."},
            ))
            return

        if action == "measure_pulse":
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "screen": "idle",
                        "message": "Запускаю мониторинг пульса (~5 мин). Держите лицо перед камерой.",
                        "assistant_source": "пульс",
                        "pulse_monitor_start": True,
                        "pulse_monitor_duration": 300,
                    },
                )
            )
            return

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "idle",
                    "message": f"Неподдерживаемая команда: {action!r}",
                },
            )
        )

    async def _start_screening(
        self,
        payload: dict[str, Any] | None = None,
        *,
        start_session: bool = True,
    ) -> None:
        if start_session:
            self._begin_session("screening", payload or {})
        self.state = SessionState.SCREENING
        self._latest_results.clear()
        self._pending_capture_mode = ""

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "screening",
                    "message": "Скрининг запущен. Держите лицо перед камерой (~20 сек).",
                    "history_count": self.history_count,
                    "assistant_source": "скрининг",
                },
            )
        )
        # Screening now uses browser-side frame capture via /ws/rppg WebSocket.
        # No camera worker capture is triggered here.

    async def _start_appearance_analysis(self) -> None:
        self.state = SessionState.APPEARANCE
        self._latest_results.clear()
        self._pending_capture_mode = "appearance_check"

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "assistant",
                    "message": "Смотрю в камеру и оцениваю внешний вид.",
                    "assistant_source": "визуальный анализ",
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.PREPARE_SESSION,
                source=self.name,
                payload={"mode": "appearance_check", "require_microphone": False},
            )
        )

    async def _handle_devices_resolved(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or self._pending_capture_mode)
        if not mode:
            return

        await self.bus.publish(
            Event(
                topic=Topics.START_CAPTURE,
                source=self.name,
                payload={
                    "mode": mode,
                    "selected_devices": payload.get("selected_devices") or {},
                },
            )
        )

        # Voice baseline test is no longer launched here —
        # MoCA is started after face scan completes (see _maybe_finish_screening)

        self._pending_capture_mode = ""

    async def _handle_device_validation_failed(self, payload: dict[str, Any]) -> None:
        errors = payload.get("errors") or []
        logger.warning(
            "Device validation failed during %s: %s",
            self._pending_capture_mode or self.state,
            "; ".join(map(str, errors)) or "unknown error",
        )
        if not self._pending_capture_mode:
            self.state = SessionState.IDLE
            self._fail_session("; ".join(map(str, errors)) or "Ошибка проверки устройства.")

    async def _finish_appearance_analysis(self, payload: dict[str, Any]) -> None:
        self.state = SessionState.REPORTING
        response_text = await self.appearance_composer.compose(payload)
        report_payload = {
            "report_type": "appearance",
            "state": "completed",
            "compliment": response_text,
            "observed": payload.get("observed") or "",
            "appearance_description": payload.get("appearance_description") or "",
            "appearance_checklist": payload.get("appearance_checklist") or {},
            "appearance_memory_notes": payload.get("appearance_memory_notes") or "",
            "wellness_suggestion": payload.get("wellness_suggestion") or "",
            "suggestion": "Можно повторить анализ после изменения света или положения камеры.",
            "face_detected": payload.get("face_detected"),
            "face_count": payload.get("face_count"),
            "confidence": payload.get("confidence"),
            "emotion": payload.get("emotion") or "",
            "estimated_age": payload.get("estimated_age"),
            "estimated_gender": payload.get("estimated_gender") or "",
            "emotiefflib_available": payload.get("emotiefflib_available"),
            "notes": payload.get("notes") or "",
            "source_backend": payload.get("source_backend") or "vision_worker",
        }

        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source=self.name, payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": response_text,
                    "report": report_payload,
                    "assistant_source": "визуальный анализ",
                },
            )
        )

        self.state = SessionState.IDLE

    async def _maybe_finish_screening(self) -> None:
        """Called when face scan result arrives — show heart rate, then launch HADS."""
        import asyncio
        if self.state != SessionState.SCREENING:
            logger.info("[aggregator] _maybe_finish_screening skipped: state=%s", self.state)
            return
        if "video" not in self._latest_results:
            logger.info("[aggregator] _maybe_finish_screening skipped: no video result yet")
            return

        # Guard against double-entry (e.g. second ANALYSIS_RESULT arriving during sleep)
        self.state = SessionState.HADS

        video = self._latest_results["video"]
        hr_bpm = video.get("heart_rate_bpm")
        hr_status = video.get("heart_rate_status", "unavailable")
        hr_algo = video.get("heart_rate_algorithm", "")
        logger.info(
            "[aggregator] screening done: heart_rate_bpm=%s status=%s algo=%s video_keys=%s",
            hr_bpm, hr_status, hr_algo, list(video.keys()),
        )

        if hr_bpm is not None:
            hr_line = f"Пульс: {hr_bpm} уд/мин ({hr_algo})."
        elif hr_status == "disabled":
            hr_line = "Измерение пульса отключено, поэтому его не будет в результате."
        else:
            hr_line = "Пульс не удалось измерить, поэтому его не будет в результате."

        # Show heart rate result on screening screen before switching to HADS
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "screening",
                    "message": (
                        f"Видео-скрининг завершён. {hr_line} "
                        "Ничего нажимать не нужно: через 8 секунд начнётся тест на тревожность."
                    ),
                    "heart_rate_bpm": hr_bpm,
                    "heart_rate_status": hr_status,
                    "heart_rate_algorithm": hr_algo,
                    "assistant_source": "скрининг",
                },
            )
        )

        # Give the patient time to see and hear the heart rate result
        # before the anxiety test takes over the screen and the speaker
        await asyncio.sleep(8.0)

        if self.state == SessionState.HADS:
            await self._start_hads(chain=True, payload={"audio_allowed": self._session_permissions.get("audio", False)})

    async def _start_moca_standalone(
        self,
        payload: dict[str, Any] | None = None,
        *,
        start_session: bool = True,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        """Launch the MoCA voice test directly from the main menu."""
        payload = payload or {}
        if start_session:
            self._begin_session("moca", payload)
        self.state = SessionState.MOCA
        self._latest_results.pop("moca", None)
        self._screening_chain = False

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "moca",
                    "message": (
                        "Сейчас начнётся голосовой тест MoCA — следуйте инструкциям."
                    ),
                    "moca_task_index": 0,
                    "moca_task_total": 11,
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.MOCA_START,
                source=self.name,
                payload={"resume_checkpoint": checkpoint or {},
                         "session_id": self._active_session_id},
            )
        )

    async def _start_hads(
        self,
        *,
        chain: bool,
        payload: dict[str, Any] | None = None,
        start_session: bool = True,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        """Launch the HADS anxiety/depression test.

        ``chain=True`` means it runs as the second step of the basic screening
        and the final report should combine video + HADS results.
        """
        payload = payload or {}
        audio_allowed = bool(payload.get("audio_allowed", self._session_permissions.get("audio", False)))
        if not chain and start_session:
            self._begin_session("hads", payload)
        self.state = SessionState.HADS
        self._screening_chain = chain
        if not chain:
            self._latest_results.pop("video", None)
        self._latest_results.pop("hads", None)

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "hads",
                    "message": (
                        "Начинается тест на тревожность и депрессию (HADS). "
                        + (
                            "Отвечайте голосом или нажимайте на вариант ответа."
                            if audio_allowed
                            else "Выбирайте ответ нажатием на экран."
                        )
                    ),
                    "hads_question_index": 0,
                    "hads_question_total": 14,
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.HADS_START,
                source=self.name,
                payload={
                    "audio_allowed": audio_allowed,
                    "session_id": self._active_session_id,
                    "resume_checkpoint": checkpoint or {},
                },
            )
        )

    def _begin_session(self, scenario: str, payload: dict[str, Any]) -> None:
        if self.session_store is None or not self._active_user_id:
            return
        if self._active_session_id:
            self.session_store.interrupt(
                self._active_session_id,
                "Начат новый сценарий до завершения предыдущего.",
            )
        stt_model = self.settings.stt_model_name if self.settings is not None else ""
        emotion_model = self.settings.emotion_model_name if self.settings is not None else ""
        record = self.session_store.start(
            user_id=self._active_user_id,
            scenario=scenario,
            versions=session_version_manifest(
                scenario,
                stt_model=stt_model,
                emotion_model=emotion_model,
            ),
            technical_params=dict(payload.get("session_conditions") or self._session_conditions),
            permissions={
                "audio": bool(payload.get("audio_allowed", False)),
                "video": bool(payload.get("video_allowed", False)),
            },
        )
        self._active_session_id = str(record.get("session_id") or "")

    async def _publish_consent_required(self, data_type: str) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "idle",
                    "message": f"Для запуска требуется согласие на обработку {data_type}.",
                },
            )
        )

    def _interrupt_session(self, reason: str) -> None:
        if self.session_store is not None and self._active_session_id:
            self.session_store.interrupt(self._active_session_id, reason)
        self._active_session_id = ""

    def _fail_session(self, reason: str) -> None:
        if self.session_store is not None and self._active_session_id:
            self.session_store.fail(self._active_session_id, reason)
        self._active_session_id = ""

    def _complete_report(self, report: dict[str, Any]) -> dict[str, Any]:
        if self.session_store is None or not self._active_session_id:
            return report
        current = self.session_store.get(self._active_session_id) or {}
        report["session_id"] = self._active_session_id
        report["user_id"] = current.get("user_id", self._active_user_id)
        report["session_started_at"] = current.get("started_at")
        report["versions"] = current.get("versions") or {}
        completed = self.session_store.complete(self._active_session_id, report) or {}
        report["session_status"] = completed.get("status", "completed")
        report["session_finished_at"] = completed.get("finished_at")
        self._active_session_id = ""
        return report

    async def _resume_session(self, session_id: str, payload: dict[str, Any] | None = None) -> None:
        if self.session_store is None or not session_id or not self._active_user_id:
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "screen": "idle",
                        "message": "Незавершенная сессия не найдена.",
                    },
                )
            )
            return
        try:
            previous = self.session_store.get(session_id)
            if previous is None or previous.get("user_id") != self._active_user_id:
                raise KeyError(session_id)
            permissions = {
                "audio": bool((payload or {}).get("audio_allowed", False)),
                "video": bool((payload or {}).get("video_allowed", False)),
            }
            scenario = previous.get("scenario")
            if scenario == "moca" and not permissions["audio"]:
                await self._publish_consent_required("аудиоданных")
                return
            if scenario == "screening" and not permissions["video"]:
                await self._publish_consent_required("видеоданных")
                return
            record = self.session_store.resume(
                session_id, user_id=self._active_user_id, permissions=permissions,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "screen": "idle",
                        "message": f"Не удалось возобновить сессию: {exc}",
                    },
                )
            )
            return

        self._active_session_id = session_id
        self._session_conditions = dict(record.get("technical_params") or {})
        self._session_permissions = dict(record.get("permissions") or {})
        checkpoint = dict(record.get("checkpoint") or {})
        scenario = str(record.get("scenario") or "")
        self._latest_results.clear()

        if scenario == "moca":
            await self._start_moca_standalone(
                {"audio_allowed": self._session_permissions.get("audio", True)},
                start_session=False,
                checkpoint=checkpoint,
            )
            return
        if scenario == "hads":
            await self._start_hads(
                chain=False,
                payload={"audio_allowed": self._session_permissions.get("audio", True)},
                start_session=False,
                checkpoint=checkpoint,
            )
            return
        if scenario == "screening" and checkpoint.get("source") == "hads":
            if isinstance(checkpoint.get("video"), dict):
                self._latest_results["video"] = dict(checkpoint["video"])
            await self._start_hads(
                chain=True,
                payload={"audio_allowed": self._session_permissions.get("audio", True)},
                start_session=False,
                checkpoint=checkpoint,
            )
            return
        if scenario == "screening":
            await self._start_screening(start_session=False)
            return
        self._fail_session("Неизвестный тип сценария при возобновлении.")

    def _conditions_limitation(self) -> str:
        """Пометка об ограничении результата условиями (ТЗ 6.3.10)."""
        conditions = self._session_conditions
        if not conditions:
            return ""
        problems = []
        if conditions.get("brightness_ok") is False:
            problems.append("слабое освещение")
        if conditions.get("face_detected") is False:
            problems.append("лицо не было видно при проверке")
        if conditions.get("noise_ok") is False:
            problems.append("фоновый шум")
        if conditions.get("voice_ok") is False:
            problems.append("тихий голос")
        if not problems:
            return ""
        return (
            "Результат может быть ограничен условиями прохождения: "
            + ", ".join(problems) + "."
        )

    async def _finish_hads(self) -> None:
        """Called when the HADS result arrives — publish the report."""
        if self.state != SessionState.HADS:
            return

        self.state = SessionState.REPORTING
        chained = self._screening_chain
        self._screening_chain = False

        video = self._latest_results.get("video", {})
        hads = self._latest_results.get("hads", {})
        if hads.get("stopped_early"):
            self._interrupt_session("HADS прерван до получения всех ответов.")
            self.state = SessionState.IDLE
            return

        hads_domains = {
            "hads_anxiety_score": hads.get("anxiety_score"),
            "hads_anxiety_max": hads.get("anxiety_max"),
            "hads_depression_score": hads.get("depression_score"),
            "hads_depression_max": hads.get("depression_max"),
            "hads_answered_count": hads.get("answered_count"),
            "hads_question_count": hads.get("question_count"),
        }
        hads_summary = {
            "hads_anxiety_interpretation": hads.get("anxiety_interpretation", ""),
            "hads_depression_interpretation": hads.get("depression_interpretation", ""),
            "hads_notes": hads.get("notes", ""),
            "limitations": self._conditions_limitation(),
        }

        if chained:
            report_payload = {
                "report_type": "screening",
                "state": "needs_review",
                "session_conditions": dict(self._session_conditions),
                "domains": {
                    "attention": video.get("attention_score"),
                    "gaze": video.get("gaze_stability"),
                    "heart_rate_bpm": video.get("heart_rate_bpm"),
                    "heart_rate_status": video.get("heart_rate_status"),
                    "heart_rate_algorithm": video.get("heart_rate_algorithm"),
                    **hads_domains,
                },
                "summary": hads_summary,
                "sources": {"video": video, "hads": hads},
            }
            anx = hads.get("anxiety_score")
            dep = hads.get("depression_score")
            message = (
                "Базовый скрининг завершён. "
                f"Тревога: {anx} из 21 ({hads.get('anxiety_interpretation', '')}). "
                f"Депрессия: {dep} из 21 ({hads.get('depression_interpretation', '')})."
            )
        else:
            report_payload = {
                "report_type": "hads",
                "state": "completed",
                "session_conditions": dict(self._session_conditions),
                "domains": hads_domains,
                "summary": hads_summary,
                "sources": {"hads": hads},
            }
            message = (
                "Тест на тревожность завершён. "
                f"Тревога: {hads.get('anxiety_score')} из 21 "
                f"({hads.get('anxiety_interpretation', '')}). "
                f"Депрессия: {hads.get('depression_score')} из 21 "
                f"({hads.get('depression_interpretation', '')})."
            )

        report_payload = self._complete_report(report_payload)
        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source=self.name, payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": message,
                    "report": report_payload,
                    "assistant_source": "тест HADS" if not chained else "скрининг",
                },
            )
        )

        self.state = SessionState.IDLE

    async def _finish_moca(self) -> None:
        """Called when MoCA test result arrives — compile and publish final report."""
        if self.state != SessionState.MOCA:
            return

        self.state = SessionState.REPORTING

        video = self._latest_results.get("video", {})
        moca = self._latest_results.get("moca", {})
        if moca.get("stopped_early"):
            self._interrupt_session("MoCA прерван до завершения теста.")
            self.state = SessionState.IDLE
            return

        report_payload = {
            "report_type": "moca",
            "state": "needs_review",
            "session_conditions": dict(self._session_conditions),
            "domains": {
                "attention": video.get("attention_score"),
                "gaze": video.get("gaze_stability"),
                "heart_rate_bpm": video.get("heart_rate_bpm"),
                "heart_rate_status": video.get("heart_rate_status"),
                "heart_rate_algorithm": video.get("heart_rate_algorithm"),
                "moca_score": moca.get("score"),
                "moca_max_score": moca.get("max_score"),
                "moca_percent": moca.get("percent"),
                "moca_tasks": moca.get("tasks", []),
                "moca_task_count": moca.get("task_count", 0),
            },
            "summary": {
                "moca_interpretation": moca.get("interpretation", ""),
                "moca_notes": moca.get("notes", ""),
                "limitations": self._conditions_limitation(),
            },
            "sources": {
                "video": video,
                "moca": moca,
            },
        }

        report_payload = self._complete_report(report_payload)
        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source=self.name, payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": "Тест MoCA завершён. Все задания выполнены.",
                    "report": report_payload,
                    "assistant_source": "тест MoCA",
                },
            )
        )

        self.state = SessionState.IDLE

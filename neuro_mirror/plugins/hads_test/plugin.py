"""HADS anxiety/depression test plugin (тест на тревожность).

Runs the 14 HADS questions sequentially. For every question:
  - Sends UI_UPDATE so the browser shows the question and the 4 answer options
  - Speaks the question and options via browser TTS (same mechanism as MoCA)
  - Accepts the answer EITHER as a click on an option (UI_ACTION "hads_answer")
    OR by voice: records via server microphone, transcribes through
    SpeechWorkerPlugin and matches the transcript to an option
  - Unrecognized voice answers are re-asked up to VOICE_RETRIES times;
    clicking always works, including while recording
After all questions publishes HADS_TEST_RESULT with both subscale scores.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.screening.hads_scoring import (
    HADS_QUESTIONS,
    PART_LABELS,
    HadsQuestion,
    match_hads_answer,
    score_hads,
)
from neuro_mirror.utils.audio import VoiceRecorder

logger = logging.getLogger(__name__)

VOICE_RETRIES = 2          # voice attempts before falling back to click-only
RECORD_SECONDS = 12.0      # max recording time per voice attempt
CLICK_WAIT_SECONDS = 180.0 # how long to wait for a click after voice attempts


class HadsTestPlugin(ProcessorPlugin):
    """Runs the HADS questionnaire with combined click + voice input."""

    plugin_name = "hads_test"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self._running = False
        self._stop_requested = False
        self._test_task: asyncio.Task[None] | None = None
        self._tts_sequence = 0
        self._tts_waiters: dict[str, asyncio.Future[bool]] = {}
        self._answer_waiter: asyncio.Future[int] | None = None
        self._current_question_index = -1

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.HADS_START, Topics.HADS_STOP, Topics.UI_ACTION)

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.HADS_STOP:
            if self._running:
                logger.info("hads_test: получен запрос на остановку")
                self._stop_requested = True
                self._resolve_pending_tts(False)
                self._cancel_answer_waiter()
                # Cancel the task outright so a long await (recording,
                # transcription) doesn't keep the test "running" for
                # up to two more minutes and block a restart
                if self._test_task is not None:
                    self._test_task.cancel()
            return

        if event.topic == Topics.UI_ACTION:
            action = str(event.payload.get("action") or event.payload.get("command") or "")
            if action == "hads_tts_finished":
                self._handle_tts_finished(event.payload)
            elif action == "hads_answer":
                self._handle_click_answer(event.payload)
            return

        # HADS_START
        if self._running:
            logger.warning("hads_test: тест уже выполняется, игнорирую повторный запуск")
            return
        self._running = True
        self._stop_requested = False
        self._test_task = asyncio.create_task(self._run_test_guarded(), name="hads-test-run")

    async def on_stop(self) -> None:
        if self._test_task is not None:
            self._test_task.cancel()
            try:
                await self._test_task
            except asyncio.CancelledError:
                pass
            self._test_task = None
        self._resolve_pending_tts(False)
        self._cancel_answer_waiter()

    # ── Test loop ───────────────────────────────────────────────────────────────

    async def _run_test_guarded(self) -> None:
        try:
            await self._run_test()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("hads_test: ошибка выполнения теста")
        finally:
            self._resolve_pending_tts(False)
            self._cancel_answer_waiter()
            self._running = False
            self._stop_requested = False
            self._test_task = None

    async def _run_test(self) -> None:
        answers: list[dict[str, Any]] = []
        total = len(HADS_QUESTIONS)

        intro = (
            "Начинаем тест на тревожность и депрессию. "
            "Я буду читать утверждения и варианты ответа. "
            "Выберите вариант, который лучше всего описывает ваше состояние "
            "за последнюю неделю. Отвечайте голосом — назовите номер варианта — "
            "или нажимайте на вариант на экране."
        )
        await self._publish_question_ui(None, -1, total, message="Приготовьтесь...")
        await self._speak(intro, screen_payload=self._question_payload(None, -1, total))

        loop = asyncio.get_running_loop()
        for idx, question in enumerate(HADS_QUESTIONS):
            if self._stop_requested:
                break
            self._current_question_index = idx

            # The answer waiter is created BEFORE the question is spoken so a
            # click on an option interrupts the TTS instead of being ignored
            waiter: asyncio.Future[int] = loop.create_future()
            self._answer_waiter = waiter

            await self._publish_question_ui(question, idx, total)
            prompt = self._build_prompt(question, idx)
            await self._speak(
                prompt,
                screen_payload=self._question_payload(question, idx, total),
                abort_future=waiter,
            )

            option_index = await self._wait_for_answer(question, idx, total, waiter)
            self._current_question_index = -1
            if option_index is None:
                if self._stop_requested:
                    break
                # No answer at all — stop the test to avoid a misleading score
                logger.warning("hads_test: нет ответа на вопрос %s, прерываю тест", question.question_id)
                self._stop_requested = True
                break

            option = question.options[option_index]
            answers.append({
                "question_id": question.question_id,
                "part": question.part,
                "question": question.text,
                "option_index": option_index,
                "option_text": option.text,
                "score": option.score,
            })
            logger.info(
                "hads_test [%s]: вариант %d (%s) = %d баллов",
                question.question_id, option_index + 1, option.text, option.score,
            )

            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    **self._question_payload(question, idx, total),
                    "hads_selected_option": option_index,
                    "hads_recording": False,
                    "message": f"Ответ принят: {option.text}",
                },
            ))
            await asyncio.sleep(0.9)

        stopped_early = self._stop_requested
        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                # On early stop the aggregator has already switched the UI to idle —
                # don't drag it back to the test screen
                "screen": "idle" if stopped_early else "hads",
                "hads_recording": False,
                "hads_stopped": stopped_early,
                "hads_question_index": total,
                "hads_question_total": total,
                "message": "Тест прерван." if stopped_early else "Тест завершён. Считаю результат...",
            },
        ))

        scoring = score_hads(answers)
        scoring["stopped_early"] = stopped_early
        await self.bus.publish(Event(
            topic=Topics.HADS_TEST_RESULT,
            source=self.name,
            payload=scoring,
        ))

    # ── Answer waiting: click future + voice attempts ───────────────────────────

    async def _wait_for_answer(
        self,
        question: HadsQuestion,
        idx: int,
        total: int,
        waiter: asyncio.Future[int],
    ) -> int | None:
        try:
            for attempt in range(VOICE_RETRIES + 1):
                if self._stop_requested or waiter.done():
                    break

                transcript = await self._record_while_waiting(waiter, question, idx, total)
                if waiter.done() or self._stop_requested:
                    break

                if transcript:
                    matched = match_hads_answer(transcript, question.options)
                    if matched is not None:
                        return matched
                    logger.info("hads_test: не распознан ответ из %r", transcript[:80])

                if attempt < VOICE_RETRIES:
                    await self._speak(
                        "Не расслышал. Назовите номер варианта — один, два, три или четыре — "
                        "или нажмите на вариант на экране.",
                        screen_payload=self._question_payload(question, idx, total),
                        abort_future=waiter,
                    )

            if waiter.done():
                return waiter.result()
            if self._stop_requested:
                return None

            # Voice failed — wait for a click only
            await self._speak(
                "Пожалуйста, выберите вариант ответа нажатием на экране.",
                screen_payload=self._question_payload(question, idx, total),
                abort_future=waiter,
            )
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    **self._question_payload(question, idx, total),
                    "hads_recording": False,
                    "message": "Выберите вариант ответа на экране.",
                },
            ))
            try:
                return await asyncio.wait_for(
                    asyncio.shield(waiter), timeout=CLICK_WAIT_SECONDS
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return None
        finally:
            if self._answer_waiter is waiter:
                self._answer_waiter = None
            if not waiter.done():
                waiter.cancel()

    async def _record_while_waiting(
        self,
        waiter: asyncio.Future[int],
        question: HadsQuestion,
        idx: int,
        total: int,
    ) -> str:
        """Record one voice attempt; abort early if a click answer arrives."""
        recorder = VoiceRecorder(
            sample_rate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
            max_seconds=RECORD_SECONDS,
            silence_threshold=self.settings.voice_silence_threshold,
            silence_duration=self.settings.voice_silence_duration,
            min_speech_duration=self.settings.voice_min_speech_duration,
        )
        if not recorder.available:
            logger.warning("hads_test: микрофон недоступен — остаётся только клик")
            try:
                await asyncio.wait_for(asyncio.shield(waiter), timeout=CLICK_WAIT_SECONDS)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            return ""

        try:
            audio_path = recorder.start()
        except Exception:
            logger.exception("hads_test: ошибка старта записи")
            return ""

        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                **self._question_payload(question, idx, total),
                "hads_recording": True,
                "message": "Говорите или нажмите вариант...",
            },
        ))

        try:
            deadline = RECORD_SECONDS + 0.5
            elapsed = 0.0
            poll = 0.2
            while elapsed < deadline:
                await asyncio.sleep(poll)
                elapsed += poll
                if not recorder.recording:
                    break
                if waiter.done() or self._stop_requested:
                    break
            audio_path = recorder.stop() or audio_path
        except Exception:
            logger.exception("hads_test: ошибка записи")
            try:
                recorder.stop()
            except Exception:
                pass
            return ""

        if waiter.done() or self._stop_requested:
            return ""

        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                **self._question_payload(question, idx, total),
                "hads_recording": False,
                "message": "Распознаю ответ...",
            },
        ))
        return await self._transcribe(audio_path)

    def _handle_click_answer(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        try:
            question_index = int(payload.get("question_index", -1))
            option_index = int(payload.get("option_index", -1))
        except (TypeError, ValueError):
            return
        if question_index != self._current_question_index:
            logger.info(
                "hads_test: клик по устаревшему вопросу %s (текущий %s)",
                question_index, self._current_question_index,
            )
            return
        if not 0 <= option_index <= 3:
            return
        waiter = self._answer_waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(option_index)

    def _cancel_answer_waiter(self) -> None:
        waiter = self._answer_waiter
        if waiter is not None and not waiter.done():
            waiter.cancel()
        self._answer_waiter = None

    # ── UI / TTS helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _question_payload(
        question: HadsQuestion | None, idx: int, total: int
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "screen": "hads",
            "hads_question_index": max(idx, 0),
            "hads_question_total": total,
            "hads_selected_option": None,
        }
        if question is not None:
            payload.update({
                "hads_question_id": question.question_id,
                "hads_part": PART_LABELS.get(question.part, question.part),
                "hads_question_text": question.text,
                "hads_options": [option.text for option in question.options],
            })
        else:
            payload.update({
                "hads_question_id": "",
                "hads_part": "",
                "hads_question_text": "",
                "hads_options": [],
            })
        return payload

    async def _publish_question_ui(
        self,
        question: HadsQuestion | None,
        idx: int,
        total: int,
        *,
        message: str = "",
    ) -> None:
        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                **self._question_payload(question, idx, total),
                "hads_recording": False,
                "message": message or (
                    f"Вопрос {idx + 1} из {total}" if question is not None else ""
                ),
            },
        ))

    @staticmethod
    def _build_prompt(question: HadsQuestion, idx: int) -> str:
        number_words = ("Один", "Два", "Три", "Четыре")
        options_spoken = ". ".join(
            f"{number_words[i]} — {option.text}"
            for i, option in enumerate(question.options)
        )
        return (
            f"Вопрос {idx + 1}. {question.text}. "
            f"Варианты ответа. {options_spoken}. "
            "Назовите номер ответа."
        )

    async def _speak(
        self,
        text: str,
        *,
        screen_payload: dict[str, Any],
        abort_future: asyncio.Future | None = None,
    ) -> bool:
        """Send TTS text to the browser and wait until playback finishes.

        If ``abort_future`` resolves first (the user answered by click while
        the question was still being spoken), stop waiting immediately —
        the browser stops the audio on its own when the answer is accepted.
        """
        if not text:
            return True
        if abort_future is not None and abort_future.done():
            return False

        self._tts_sequence += 1
        tts_id = f"hads-{self._tts_sequence}"
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[bool] = loop.create_future()
        self._tts_waiters[tts_id] = waiter

        try:
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    **screen_payload,
                    "hads_tts_id": tts_id,
                    "hads_tts_text": text,
                    "hads_recording": False,
                    "message": "Слушайте вопрос...",
                },
            ))
            timeout = self._tts_timeout_seconds(text)
            if abort_future is not None and not abort_future.done():
                done, _ = await asyncio.wait(
                    {waiter, abort_future},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if abort_future in done:
                    logger.info("hads_test: TTS %s прерван ответом пользователя", tts_id)
                    return False
                if waiter in done:
                    return waiter.result()
                logger.warning("hads_test: TTS playback confirmation timed out for %s", tts_id)
                return False
            await asyncio.wait_for(waiter, timeout=timeout)
            return waiter.result()
        except asyncio.TimeoutError:
            logger.warning("hads_test: TTS playback confirmation timed out for %s", tts_id)
            return False
        finally:
            self._tts_waiters.pop(tts_id, None)

    @staticmethod
    def _tts_timeout_seconds(text: str) -> float:
        words = len(text.split())
        estimated = words / 2.2 + 6.0
        return min(90.0, max(5.0, estimated))

    def _handle_tts_finished(self, payload: dict[str, Any]) -> None:
        tts_id = str(payload.get("hads_tts_id") or "")
        waiter = self._tts_waiters.pop(tts_id, None)
        if waiter is not None and not waiter.done():
            waiter.set_result(True)

    def _resolve_pending_tts(self, result: bool) -> None:
        for waiter in list(self._tts_waiters.values()):
            if not waiter.done():
                waiter.set_result(result)
        self._tts_waiters.clear()

    async def _transcribe(self, audio_path: str) -> str:
        try:
            reply = await self.bus.request(
                Event(
                    topic=Topics.REQ_SPEECH_TRANSCRIBE,
                    source=self.name,
                    payload={"audio_path": audio_path, "suppress_ui": True},
                ),
                timeout=120.0,
            )
            return str(reply.get("transcript") or "")
        except Exception as exc:
            logger.warning("hads_test: transcribe error: %s", exc)
            return ""

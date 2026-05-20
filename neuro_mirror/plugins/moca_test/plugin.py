"""MoCA (Montreal Cognitive Assessment) voice test plugin.

Runs 11 tasks sequentially:
  1.  Memory — repeat 5 words (attempt 1)
  2.  Memory — repeat 5 words (attempt 2)
  3.  Attention — digit span forward  (2-1-8-5-4)
  4.  Attention — digit span backward (7-4-2 → answer 2-4-7)
  5.  Attention — serial subtraction 100−7 (five times)
  6.  Language — repeat sentence 1
  7.  Language — repeat sentence 2
  8.  Language — verbal fluency (words starting with Л, 1 min)
  9.  Abstraction — pair 1 (train / bicycle)
  10. Abstraction — pair 2 (watch / ruler)
  11. Delayed recall (same 5 words from task 1)

Each task:
  - Sends UI_UPDATE so the browser shows the current task text and progress
  - Requests TTS via /api/tts/speak (HTTP POST to the local web server)
  - Waits for TTS audio duration + a short buffer
  - Records the patient's voice response
  - Transcribes it via SpeechWorkerPlugin (REQ_SPEECH_TRANSCRIBE)
  - Stores the transcript for that task
After all tasks publishes MOCA_TEST_RESULT with all transcripts and metadata.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.screening.moca_scoring import score_moca_tasks
from neuro_mirror.utils.audio import VoiceRecorder

logger = logging.getLogger(__name__)

# ── Task definitions ───────────────────────────────────────────────────────────

@dataclass
class MocaTask:
    task_id: str
    domain: str
    prompt: str          # spoken to the patient via TTS
    max_record_seconds: float = 15.0
    hint: str = ""       # shown in UI only


MOCA_TASKS: list[MocaTask] = [
    MocaTask(
        task_id="memory_1",
        domain="Память",
        prompt=(
            "Сейчас я назову пять слов. Слушайте внимательно "
            "и повторите их все, когда я закончу. "
            "Лицо. Бархат. Церковь. Фиалка. Красный. "
            "Повторите эти слова."
        ),
        max_record_seconds=20.0,
        hint="Повторите 5 слов",
    ),
    MocaTask(
        task_id="memory_2",
        domain="Память",
        prompt=(
            "Я снова назову те же слова. Постарайтесь запомнить — "
            "они понадобятся вам в конце. "
            "Лицо. Бархат. Церковь. Фиалка. Красный. "
            "Повторите."
        ),
        max_record_seconds=20.0,
        hint="Повторите 5 слов (попытка 2)",
    ),
    MocaTask(
        task_id="attention_digits_forward",
        domain="Внимание",
        prompt=(
            "Я назову цифры. Повторите их точно в том же порядке. "
            "Два. Один. Восемь. Пять. Четыре."
        ),
        max_record_seconds=12.0,
        hint="Повторите цифры по порядку",
    ),
    MocaTask(
        task_id="attention_digits_backward",
        domain="Внимание",
        prompt=(
            "Теперь я назову цифры, а вы повторите их "
            "в обратном порядке — с конца к началу. "
            "Семь. Четыре. Два. "
            "Назовите в обратном порядке."
        ),
        max_record_seconds=12.0,
        hint="Назовите цифры в обратном порядке",
    ),
    MocaTask(
        task_id="attention_serial",
        domain="Счёт",
        prompt=(
            "Сейчас мы будем считать. "
            "Я скажу число, вы отнимите от него семь и назовёте результат. "
            "Готовы? Начинаем со ста. Сколько будет сто минус семь?"
        ),
        max_record_seconds=12.0,
        hint="Назовите результат",
    ),
    MocaTask(
        task_id="language_sentence_1",
        domain="Речь",
        prompt=(
            "Я произнесу предложение. Повторите его слово в слово, "
            "как можно точнее. "
            "Я знаю только одно, что Иван — это тот, кто может сегодня помочь. "
            "Повторите."
        ),
        max_record_seconds=18.0,
        hint="Повторите предложение",
    ),
    MocaTask(
        task_id="language_sentence_2",
        domain="Речь",
        prompt=(
            "Ещё одно предложение. Повторите слово в слово. "
            "Кошка всегда пряталась под диваном, когда собаки были в комнате. "
            "Повторите."
        ),
        max_record_seconds=18.0,
        hint="Повторите предложение",
    ),
    MocaTask(
        task_id="language_fluency",
        domain="Речь",
        prompt=(
            "За одну минуту назовите как можно больше слов, "
            "которые начинаются на букву Л. "
            "Имена людей не считаются. Начните."
        ),
        max_record_seconds=65.0,
        hint="Слова на букву Л — 1 минута",
    ),
    MocaTask(
        task_id="abstraction_1",
        domain="Абстракция",
        prompt=(
            "Скажите, что общего между этими двумя предметами. "
            "Поезд и велосипед."
        ),
        max_record_seconds=15.0,
        hint="Что общего?",
    ),
    MocaTask(
        task_id="abstraction_2",
        domain="Абстракция",
        prompt=(
            "Ещё два предмета. Что у них общего? "
            "Часы и линейка."
        ),
        max_record_seconds=15.0,
        hint="Что общего?",
    ),
    MocaTask(
        task_id="delayed_recall",
        domain="Память (отсроченная)",
        prompt=(
            "В самом начале я просил вас запомнить пять слов. "
            "Назовите их сейчас — все, которые помните."
        ),
        max_record_seconds=30.0,
        hint="Назовите запомненные слова",
    ),
]

# Serial subtraction steps: after the first prompt above we continue step-by-step
SERIAL_SUBTRACTION_STEPS = [
    ("Теперь от данного числа отнимите семь. Сколько получилось?", 86),
    ("Теперь от данного числа отнимите семь. Сколько получилось?", 79),
    ("Ещё раз: от данного числа отнимите семь.", 72),
    ("И последний раз: от данного числа отнимите семь.", 65),
]


class MocaTestPlugin(ProcessorPlugin):
    """Runs a full MoCA voice screening and publishes the result."""

    plugin_name = "moca_test"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self._running = False
        self._stop_requested = False
        self._test_task: asyncio.Task[None] | None = None
        self._tts_sequence = 0
        self._tts_waiters: dict[str, asyncio.Future[bool]] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.MOCA_START, Topics.MOCA_STOP, Topics.UI_ACTION)

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.MOCA_STOP:
            if self._running:
                logger.info("moca_test: получен запрос на остановку")
                self._stop_requested = True
                self._resolve_pending_tts(False)
            return

        if event.topic == Topics.UI_ACTION:
            action = str(event.payload.get("action") or event.payload.get("command") or "")
            if action == "moca_tts_finished":
                self._handle_tts_finished(event.payload)
            return

        if self._running:
            logger.warning("moca_test: тест уже выполняется, игнорирую повторный запуск")
            return
        self._running = True
        self._stop_requested = False
        self._test_task = asyncio.create_task(self._run_test_guarded(), name="moca-test-run")

    async def on_stop(self) -> None:
        if self._test_task is not None:
            self._test_task.cancel()
            try:
                await self._test_task
            except asyncio.CancelledError:
                pass
            self._test_task = None
        self._resolve_pending_tts(False)

    async def _run_test_guarded(self) -> None:
        try:
            await self._run_test()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("moca_test: ошибка выполнения теста")
        finally:
            self._resolve_pending_tts(False)
            self._running = False
            self._stop_requested = False
            self._test_task = None

    # ── Internal ────────────────────────────────────────────────────────────────

    async def _run_test(self) -> None:
        results: list[dict[str, Any]] = []
        total = len(MOCA_TASKS)

        for idx, task in enumerate(MOCA_TASKS):
            if self._stop_requested:
                break

            # ── Update UI ──────────────────────────────────────────────────────
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "moca",
                    "moca_task_index": idx,
                    "moca_task_total": total,
                    "moca_task_id": task.task_id,
                    "moca_domain": task.domain,
                    "moca_hint": task.hint,
                    "message": f"Задание {idx + 1} из {total}: {task.domain}",
                },
            ))

            # ── Speak prompt via TTS ───────────────────────────────────────────
            tts_ok = await self._speak(task.prompt)
            if not tts_ok:
                logger.warning("moca_test: TTS не сработал для %s", task.task_id)

            # Short pause so patient knows it's their turn
            await asyncio.sleep(0.6)

            # ── Record patient response ────────────────────────────────────────
            if task.task_id == "attention_serial":
                transcript, audio_ms = await self._run_serial_subtraction(task, idx, total)
            else:
                transcript, audio_ms = await self._record_and_transcribe(task)

            results.append({
                "task_id": task.task_id,
                "domain": task.domain,
                "transcript": transcript,
                "audio_ms": audio_ms,
            })
            logger.info("moca_test [%s]: %r (%d ms)", task.task_id, transcript[:80], audio_ms)

            if self._stop_requested:
                break

            # Brief pause between tasks
            await asyncio.sleep(1.2)

        # ── Publish final result ───────────────────────────────────────────────
        stopped_early = self._stop_requested
        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                "screen": "moca",
                "moca_recording": False,
                "moca_stopped": stopped_early,
                "message": "Тест прерван." if stopped_early else "Голосовой тест завершён. Обрабатываю результаты...",
                "moca_task_index": total,
                "moca_task_total": total,
            },
        ))

        scoring = score_moca_tasks(results)

        await self.bus.publish(Event(
            topic=Topics.MOCA_TEST_RESULT,
            source=self.name,
            payload={
                "tasks": scoring["tasks"],
                "task_count": total,
                "domains": list({r["domain"] for r in results}),
                "score": scoring["score"],
                "max_score": scoring["max_score"],
                "percent": scoring["percent"],
                "interpretation": scoring["interpretation"],
                "notes": scoring["notes"],
            },
        ))

    async def _run_serial_subtraction(
        self, task: MocaTask, idx: int, total: int
    ) -> tuple[str, int]:
        """Run the 100-7 subtraction task step by step: 5 rounds."""
        all_transcripts: list[str] = []
        t_start = time.monotonic()

        # First answer already prompted by the main task prompt (100-7=?)
        transcript, _ = await self._record_and_transcribe(task)
        all_transcripts.append(transcript)

        for step_prompt, _ in SERIAL_SUBTRACTION_STEPS:
            if self._stop_requested:
                break

            # Update hint to keep screen clean
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "moca",
                    "moca_task_index": idx,
                    "moca_task_total": total,
                    "moca_task_id": task.task_id,
                    "moca_domain": task.domain,
                    "moca_hint": task.hint,
                    "moca_recording": False,
                    "message": "",
                },
            ))

            await self._speak(step_prompt)
            await asyncio.sleep(0.5)

            step_task = MocaTask(
                task_id=task.task_id,
                domain=task.domain,
                prompt="",
                max_record_seconds=10.0,
                hint=task.hint,
            )
            t, _ = await self._record_and_transcribe(step_task)
            all_transcripts.append(t)

        audio_ms = int((time.monotonic() - t_start) * 1000)
        return " | ".join(all_transcripts), audio_ms

    async def _speak(self, text: str) -> bool:
        """Send TTS text to browser and wait until playback is finished."""
        if not text:
            return True

        self._tts_sequence += 1
        tts_id = f"moca-{self._tts_sequence}"
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[bool] = loop.create_future()
        self._tts_waiters[tts_id] = waiter

        try:
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "moca",
                    "moca_tts_id": tts_id,
                    "moca_tts_text": text,
                    "moca_recording": False,
                    "message": "Слушайте вопрос...",
                },
            ))
            await asyncio.wait_for(waiter, timeout=self._tts_timeout_seconds(text))
            return waiter.result()
        except asyncio.TimeoutError:
            logger.warning("moca_test: TTS playback confirmation timed out for %s", tts_id)
            return False
        finally:
            self._tts_waiters.pop(tts_id, None)

    @staticmethod
    def _tts_timeout_seconds(text: str) -> float:
        # ~130 words/min Russian TTS = ~2.17 chars/sec; add 6s buffer for startup
        words = len(text.split())
        estimated = words / 2.2 + 6.0
        return min(60.0, max(5.0, estimated))

    def _handle_tts_finished(self, payload: dict[str, Any]) -> None:
        tts_id = str(payload.get("moca_tts_id") or "")
        waiter = self._tts_waiters.pop(tts_id, None)
        if waiter is not None and not waiter.done():
            waiter.set_result(True)

    def _resolve_pending_tts(self, result: bool) -> None:
        for waiter in list(self._tts_waiters.values()):
            if not waiter.done():
                waiter.set_result(result)
        self._tts_waiters.clear()

    async def _record_and_transcribe(self, task: MocaTask) -> tuple[str, int]:
        """Record patient audio and return (transcript, duration_ms)."""
        recorder = VoiceRecorder(
            sample_rate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
            max_seconds=task.max_record_seconds,
            silence_threshold=self.settings.voice_silence_threshold,
            silence_duration=self.settings.voice_silence_duration,
            min_speech_duration=self.settings.voice_min_speech_duration,
        )

        if not recorder.available:
            logger.warning("moca_test: микрофон недоступен")
            return "", 0

        t_start = time.monotonic()
        try:
            audio_path = recorder.start()
        except Exception as exc:
            logger.exception("moca_test: ошибка старта записи для %s", task.task_id)
            return "", 0

        # Signal UI: recording started — show mic indicator NOW
        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                "screen": "moca",
                "moca_recording": True,
                "message": "Говорите...",
            },
        ))

        try:
            # Poll until VAD stops recorder or max time reached
            deadline = task.max_record_seconds + 0.5
            elapsed = 0.0
            poll = 0.2
            last_ui_second = -1
            while elapsed < deadline:
                await asyncio.sleep(poll)
                elapsed += poll
                if not recorder.recording:
                    break
                if self._stop_requested:
                    break
                # Update countdown every second so user sees progress
                current_second = int(elapsed)
                if current_second != last_ui_second:
                    last_ui_second = current_second
                    remaining = max(0, int(task.max_record_seconds - elapsed))
                    await self.bus.publish(Event(
                        topic=Topics.UI_UPDATE,
                        source=self.name,
                        payload={
                            "screen": "moca",
                            "moca_recording": True,
                            "message": f"Говорите... ({remaining} с)",
                        },
                    ))
            audio_path = recorder.stop() or audio_path
        except Exception as exc:
            logger.exception("moca_test: ошибка записи для %s", task.task_id)
            try:
                recorder.stop()
            except Exception:
                pass
            return "", 0

        audio_ms = int((time.monotonic() - t_start) * 1000)

        # Hide mic indicator immediately after recording stops
        await self.bus.publish(Event(
            topic=Topics.UI_UPDATE,
            source=self.name,
            payload={
                "screen": "moca",
                "moca_recording": False,
                "message": "Распознаю ответ...",
            },
        ))

        # Transcribe via SpeechWorkerPlugin request-reply
        transcript = await self._transcribe(audio_path)
        return transcript, audio_ms

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
            logger.warning("moca_test: transcribe error: %s", exc)
            return ""

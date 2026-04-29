from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.screening.audio_analyzer import analyze_audio
from neuro_mirror.utils.audio import VoiceRecorder

logger = logging.getLogger(__name__)

# How many seconds to record for the voice screening test.
_TEST_RECORD_SECONDS = 5.0


class VoiceTestPlugin(ProcessorPlugin):
    """Records a short audio sample and runs speech biomarker analysis."""

    plugin_name = "voice_test"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self._recorder = VoiceRecorder(
            sample_rate=settings.voice_sample_rate,
            channels=settings.voice_channels,
            max_seconds=_TEST_RECORD_SECONDS,
        )

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.START_TEST,)

    async def handle_event(self, event: Event) -> None:
        audio_path = str(event.payload.get("audio_path") or "")

        if not audio_path:
            audio_path = await self._record_sample()

        if not audio_path:
            logger.warning("voice_test: не удалось получить аудио для анализа")
            await self.bus.publish(
                Event(
                    topic=Topics.VOICE_TEST_RESULT,
                    source=self.name,
                    payload={
                        "speech_score": 0.0,
                        "reaction_ms": 0,
                        "notes": "Не удалось записать аудио для голосового теста.",
                    },
                )
            )
            return

        try:
            result = await asyncio.to_thread(analyze_audio, audio_path)
            logger.info("voice_test: анализ завершён — speech_score=%.2f, reaction_ms=%d", result.speech_score, result.reaction_ms)

            await self.bus.publish(
                Event(
                    topic=Topics.VOICE_TEST_RESULT,
                    source=self.name,
                    payload={
                        "speech_score": result.speech_score,
                        "speech_rate_wpm": result.speech_rate_wpm,
                        "pause_ratio": result.pause_ratio,
                        "reaction_ms": result.reaction_ms,
                        "pitch_variability": result.pitch_variability,
                        "biomarker_flags": list(result.biomarker_flags),
                        "transcript": result.transcript,
                        "notes": result.notes,
                    },
                )
            )
        except Exception as exc:
            logger.exception("voice_test: ошибка анализа аудио")
            await self.bus.publish(
                Event(
                    topic=Topics.VOICE_TEST_RESULT,
                    source=self.name,
                    payload={
                        "speech_score": 0.0,
                        "reaction_ms": 0,
                        "notes": f"Ошибка аудио-анализа: {exc}",
                    },
                )
            )
        finally:
            self._cleanup_audio(audio_path)

    async def _record_sample(self) -> str:
        """Record a short audio sample using VoiceRecorder."""
        if not self._recorder.available:
            logger.warning("voice_test: sounddevice недоступен, запись невозможна")
            return ""

        try:
            audio_path = self._recorder.start()
            logger.info("voice_test: запись %s сек...", _TEST_RECORD_SECONDS)
            # Wait for recording to finish (max_seconds will auto-stop via CallbackStop)
            await asyncio.sleep(_TEST_RECORD_SECONDS + 0.5)
            return self._recorder.stop() or audio_path
        except Exception as exc:
            logger.exception("voice_test: ошибка записи")
            try:
                self._recorder.stop()
            except Exception:
                pass
            return ""

    @staticmethod
    def _cleanup_audio(audio_path: str) -> None:
        if not audio_path:
            return
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass

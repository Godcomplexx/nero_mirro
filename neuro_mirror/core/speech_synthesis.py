"""Локальный синтез речи.

Инструкции озвучиваются моделью, размещённой на устройстве, поэтому текст
заданий не покидает машину и проведение теста не зависит от подключения к
сети. Модель загружается один раз при первом обращении и остаётся в памяти:
на инструкцию уходит заметно меньше времени, чем длится сама фраза.
"""
from __future__ import annotations

import io
import logging
import threading
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_VOICE_PATH = Path("runtime/models/tts/ru_RU-irina-medium.onnx")


class SpeechSynthesisUnavailable(RuntimeError):
    """Синтез невозможен: нет библиотеки или файла голоса."""


class SpeechSynthesizer:
    """Обёртка над локальной моделью синтеза речи.

    Загрузка отложена до первого запроса, чтобы старт программы не ждал
    модель, и защищена блокировкой: озвучка может запрашиваться из разных
    обработчиков одновременно.
    """

    def __init__(self, voice_path: str | Path = DEFAULT_VOICE_PATH) -> None:
        self.voice_path = Path(voice_path)
        self._voice = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.voice_path.is_file()

    def _ensure_loaded(self):
        if self._voice is not None:
            return self._voice
        with self._lock:
            if self._voice is not None:
                return self._voice
            if not self.available:
                raise SpeechSynthesisUnavailable(
                    f"Файл голоса не найден: {self.voice_path}"
                )
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise SpeechSynthesisUnavailable(
                    "Библиотека синтеза речи не установлена."
                ) from exc
            logger.info("tts: загружаю голос %s", self.voice_path.name)
            self._voice = PiperVoice.load(str(self.voice_path))
            return self._voice

    def synthesize_wav(self, text: str) -> bytes:
        """Озвучить текст и вернуть WAV целиком."""
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Пустой текст для озвучивания.")
        voice = self._ensure_loaded()
        buffer = io.BytesIO()
        with self._lock:
            with wave.open(buffer, "wb") as target:
                voice.synthesize_wav(cleaned, target)
        return buffer.getvalue()

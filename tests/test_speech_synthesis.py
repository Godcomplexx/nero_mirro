"""Локальный синтез речи: доступность голоса и поведение при его отсутствии."""
from __future__ import annotations

import wave
from io import BytesIO

import pytest

from neuro_mirror.core.speech_synthesis import (
    DEFAULT_VOICE_PATH,
    SpeechSynthesisUnavailable,
    SpeechSynthesizer,
)

VOICE_PRESENT = DEFAULT_VOICE_PATH.is_file()


def test_missing_voice_file_is_reported_as_unavailable(tmp_path):
    synth = SpeechSynthesizer(tmp_path / "нет-такого-голоса.onnx")
    assert synth.available is False
    with pytest.raises(SpeechSynthesisUnavailable):
        synth.synthesize_wav("Проверка")


def test_empty_text_is_rejected_before_loading_the_model(tmp_path):
    """Пустой текст — ошибка вызывающего, а не повод грузить модель."""
    synth = SpeechSynthesizer(tmp_path / "нет-такого-голоса.onnx")
    with pytest.raises(ValueError):
        synth.synthesize_wav("   ")


def test_bundled_voice_is_present():
    """Без файла голоса инструкции не озвучиваются и тест провести нельзя."""
    assert VOICE_PRESENT, f"не найден файл голоса {DEFAULT_VOICE_PATH}"


@pytest.mark.skipif(not VOICE_PRESENT, reason="файл голоса не установлен")
def test_synthesis_returns_playable_wav():
    audio = SpeechSynthesizer().synthesize_wav("Повторите пять слов.")
    with wave.open(BytesIO(audio), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() > 0
        assert handle.getnframes() > 0


@pytest.mark.skipif(not VOICE_PRESENT, reason="файл голоса не установлен")
def test_long_instruction_is_synthesized_faster_than_it_sounds():
    """Инструкции MoCA длинные: синтез не должен растягивать паузу перед ответом."""
    import time

    synth = SpeechSynthesizer()
    synth.synthesize_wav("разогрев")  # модель грузится один раз

    text = (
        "Сейчас я назову пять слов. Слушайте внимательно и повторите их все, "
        "когда я закончу. Лицо. Бархат. Церковь. Фиалка. Красный."
    )
    started = time.perf_counter()
    audio = synth.synthesize_wav(text)
    elapsed = time.perf_counter() - started

    with wave.open(BytesIO(audio), "rb") as handle:
        duration = handle.getnframes() / handle.getframerate()
    assert duration > 5.0, "фраза должна звучать заметное время"
    assert elapsed < duration, "синтез медленнее собственной речи"


@pytest.mark.skipif(not VOICE_PRESENT, reason="файл голоса не установлен")
def test_model_is_loaded_once_and_reused():
    synth = SpeechSynthesizer()
    synth.synthesize_wav("первый")
    loaded = synth._voice
    synth.synthesize_wav("второй")
    assert synth._voice is loaded

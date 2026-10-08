"""Показатели речи и видео: что измеряется и что остаётся пустым.

Прежде оба разбора были заглушками и не возвращали ничего, хотя измерять было
чем: запись читается, лицо детектируется. Теперь измеримое измеряется, а то,
для чего нужна утверждённая методика, остаётся пустым — подставлять вместо
неё собственную формулу нельзя, числа уходят специалисту.
"""
from __future__ import annotations

import math
import struct
import wave

import pytest

from neuro_mirror.screening.audio_analyzer import (
    MIN_DURATION_FOR_RATE_SECONDS,
    analyze_audio,
)
from neuro_mirror.screening.video_analyzer import analyze_frames

SAMPLE_RATE = 16_000
PHRASE = "кошка всегда пряталась под диваном когда собаки были в комнате"


def a_recording(tmp_path, *, lead_silence: float, speech: float,
                pause: float = 0.0, tail_speech: float = 0.0) -> str:
    """Запись с заданной тишиной в начале и паузой внутри."""
    def tone(seconds: float) -> list[int]:
        return [
            int(0.3 * 32767 * math.sin(2 * math.pi * 180 * t / SAMPLE_RATE))
            for t in range(int(SAMPLE_RATE * seconds))
        ]

    samples: list[int] = [0] * int(SAMPLE_RATE * lead_silence)
    samples += tone(speech)
    if pause:
        samples += [0] * int(SAMPLE_RATE * pause)
    if tail_speech:
        samples += tone(tail_speech)

    path = tmp_path / "answer.wav"
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(b"".join(struct.pack("<h", value) for value in samples))
    return str(path)


def a_frame(colour: int = 128) -> bytes:
    import cv2
    import numpy as np

    ok, buffer = cv2.imencode(".jpg", np.full((240, 320, 3), colour, dtype=np.uint8))
    assert ok
    return buffer.tobytes()


# ── Речь: что измеряется ──────────────────────────────────────────────────────

def test_the_delay_before_the_answer_is_measured(tmp_path):
    """Задержка ответа — обычное измерение сигнала, а не оценка."""
    path = a_recording(tmp_path, lead_silence=0.6, speech=1.5)
    result = analyze_audio(path)
    assert result.reaction_ms is not None
    assert 400 <= result.reaction_ms <= 800, result.reaction_ms


def test_the_share_of_pauses_is_measured(tmp_path):
    path = a_recording(tmp_path, lead_silence=0.1, speech=1.2, pause=0.8, tail_speech=1.0)
    result = analyze_audio(path)
    assert result.pause_ratio is not None
    assert 0.15 <= result.pause_ratio <= 0.35, result.pause_ratio


def test_the_speech_rate_needs_the_recognised_words(tmp_path):
    """Без расшифровки считать слова не из чего."""
    path = a_recording(tmp_path, lead_silence=0.1, speech=3.5)
    assert analyze_audio(path).speech_rate_wpm is None
    with_words = analyze_audio(path, PHRASE)
    assert with_words.speech_rate_wpm is not None
    assert 100 <= with_words.speech_rate_wpm <= 300, with_words.speech_rate_wpm


def test_a_recording_too_short_gives_no_rate(tmp_path):
    """На коротком отрывке одно лишнее слово меняет темп вдвое."""
    path = a_recording(tmp_path, lead_silence=0.05, speech=MIN_DURATION_FOR_RATE_SECONDS / 2)
    assert analyze_audio(path, PHRASE).speech_rate_wpm is None


def test_the_measured_acoustics_are_kept_for_the_report(tmp_path):
    path = a_recording(tmp_path, lead_silence=0.2, speech=1.0, pause=0.7, tail_speech=1.0)
    result = analyze_audio(path)
    assert result.acoustics.get("duration_seconds")
    assert result.acoustics.get("pause_count") >= 1


# ── Речь: что остаётся пустым ─────────────────────────────────────────────────

def test_the_clinical_score_is_not_invented(tmp_path):
    """Для сводной оценки речи нужна утверждённая методика."""
    result = analyze_audio(a_recording(tmp_path, lead_silence=0.2, speech=2.5), PHRASE)
    assert result.speech_score is None
    assert result.pitch_variability is None
    assert result.biomarker_flags == []
    assert "методика не утверждена" in result.notes


# ── Речь: отказы ──────────────────────────────────────────────────────────────

def test_a_missing_path_is_reported_and_not_guessed():
    result = analyze_audio("")
    assert result.reaction_ms is None
    assert "путь к аудио не задан" in result.notes


def test_an_unreadable_recording_is_reported(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a wav file at all")
    result = analyze_audio(str(broken))
    assert result.reaction_ms is None
    assert "не удалось прочитать" in result.notes.lower()


# ── Видео: что измеряется ─────────────────────────────────────────────────────

def test_the_absence_of_a_face_is_a_measurement_not_a_default():
    """Прежде разбор всегда отвечал «лицо не найдено», ничего не проверяя."""
    result = analyze_frames([a_frame()])
    assert result.face_detected is False
    assert result.face_count == 0
    assert result.detector_available is True


def test_the_last_frame_is_the_one_measured():
    """Он ближе всего к моменту замера."""
    result = analyze_frames([a_frame(0), a_frame(128)])
    assert result.detector_available is True


def test_no_frames_is_reported_and_not_passed_off_as_no_face():
    result = analyze_frames([])
    assert result.face_detected is False
    assert "кадры не получены" in result.notes.lower()


def test_empty_frames_are_skipped():
    result = analyze_frames([b"", b""])
    assert "кадры не получены" in result.notes.lower()


def test_a_broken_frame_does_not_break_the_screening():
    result = analyze_frames([b"this is not an image"])
    assert result.face_detected is False
    assert result.notes


# ── Видео: что остаётся пустым ────────────────────────────────────────────────

def test_attention_and_gaze_are_not_invented():
    result = analyze_frames([a_frame()])
    assert result.attention_score is None
    assert result.gaze_stability is None
    assert result.micro_expression_flags == []
    assert "методика не утверждена" in result.notes

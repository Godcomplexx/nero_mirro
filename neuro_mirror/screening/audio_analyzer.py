"""Показатели речи для скрининга.

Часть показателей измеряется по самой записи и считается здесь: задержка
ответа, доля пауз, темп речи. Это обычные измерения сигнала, а не клиническая
оценка.

Чего здесь нет и не выдумывается: сводная оценка речи, изменчивость высоты
голоса и перечень биомаркерных признаков. Для них нужна утверждённая
методика; подставить вместо неё собственную формулу нельзя — числа уйдут
специалисту и будут выглядеть измерением. Поля остаются пустыми, а причина
записывается в примечание.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from neuro_mirror.screening.speech_metrics import analyze_text, analyze_wav

logger = logging.getLogger(__name__)

# Темп речи считается только по записи достаточной длины: на коротком
# отрывке одно лишнее слово меняет результат вдвое.
MIN_DURATION_FOR_RATE_SECONDS = 2.0


@dataclass(slots=True)
class AudioAnalysisResult:
    """Result of audio analysis for screening."""

    speech_score: Optional[float] = None
    speech_rate_wpm: Optional[float] = None
    pause_ratio: Optional[float] = None
    reaction_ms: Optional[int] = None
    pitch_variability: Optional[float] = None
    biomarker_flags: list[str] = field(default_factory=list)
    transcript: str = ""               # ASR transcript (if available)
    notes: str = ""
    # Измеренные показатели записи целиком: длительность, паузы, речевые
    # отрезки. Пригодятся отчёту специалиста и разбору неисправности.
    acoustics: dict[str, Any] = field(default_factory=dict)


# Что именно не рассчитывается и почему — одной строкой для отчёта.
MISSING_NOTE = (
    "Сводная оценка речи, изменчивость высоты голоса и биомаркерные признаки "
    "не рассчитываются: методика не утверждена."
)


def analyze_audio(audio_path: str, transcript: str = "") -> AudioAnalysisResult:
    """Измерить показатели речи по записи.

    ``transcript`` нужен только для темпа речи: без распознанного текста
    считать слова не из чего, и темп остаётся пустым.

    Функция намеренно синхронная — вызывающий использует
    ``asyncio.to_thread(analyze_audio, path)``.
    """
    if not audio_path:
        return AudioAnalysisResult(
            transcript=transcript,
            notes="Акустические маркеры недоступны: путь к аудио не задан.",
        )

    acoustics = analyze_wav(audio_path)
    if not acoustics:
        return AudioAnalysisResult(
            transcript=transcript,
            notes="Не удалось прочитать запись: показатели речи не измерены.",
        )

    duration = float(acoustics.get("duration_seconds") or 0.0)
    first_response = acoustics.get("time_to_first_response_seconds")
    total_pause = float(acoustics.get("total_pause_seconds") or 0.0)

    reaction_ms = (
        int(round(float(first_response) * 1000))
        if isinstance(first_response, (int, float))
        else None
    )
    pause_ratio = round(total_pause / duration, 3) if duration > 0 else None

    speech_rate = None
    if transcript.strip() and duration >= MIN_DURATION_FOR_RATE_SECONDS:
        words = int(analyze_text(transcript).get("word_count") or 0)
        if words:
            speech_rate = round(words * 60.0 / duration, 1)

    return AudioAnalysisResult(
        speech_rate_wpm=speech_rate,
        pause_ratio=pause_ratio,
        reaction_ms=reaction_ms,
        transcript=transcript,
        acoustics=acoustics,
        notes=MISSING_NOTE,
    )

"""Речевые метрики для ответов в голосовых когнитивных тестах."""
from __future__ import annotations

import re
import wave
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


# Параметры пауз перенесены из SpeechMirror.py. Здесь используется только
# стандартный WAV reader и NumPy, чтобы не добавлять тяжёлую зависимость librosa.
FRAME_LENGTH = 1024
HOP_LENGTH = 256
RELATIVE_SILENCE_THRESHOLD = 0.2
MIN_PAUSE_SECONDS = 0.2
MIN_LEXICAL_WORDS = 20

FILLER_PHRASES = (
    "как бы",
    "так сказать",
    "в общем",
    "короче говоря",
)
FILLER_WORDS = {
    "э",
    "эм",
    "мм",
    "м",
    "ну",
    "вот",
    "короче",
    "типа",
    "значит",
}
CORRECTION_CUES = (
    "ой",
    "нет",
    "вернее",
    "точнее",
    "то есть",
    "исправлюсь",
    "не так",
    "я ошибся",
    "я ошиблась",
)
UNFINISHED_ENDINGS = {
    "и",
    "а",
    "но",
    "или",
    "что",
    "чтобы",
    "потому",
    "если",
    "когда",
    "который",
    "которая",
    "которые",
}


def normalize_words(text: str) -> list[str]:
    """Вернуть слова и числа в нижнем регистре без пунктуации."""
    return re.findall(r"[0-9a-zа-я]+", text.lower().replace("ё", "е"))


def analyze_text(text: str) -> dict[str, Any]:
    """Посчитать воспроизводимые лексические показатели транскрипции."""
    words = normalize_words(text)
    counts = Counter(words)
    repetitions = [
        {"text": word, "extra_occurrences": count - 1}
        for word, count in counts.items()
        if count > 1
    ]

    phrase_counts: Counter[str] = Counter()
    for size in (2, 3):
        phrase_counts.update(
            " ".join(words[index:index + size])
            for index in range(len(words) - size + 1)
        )
    repeated_phrases = [
        {"text": phrase, "extra_occurrences": count - 1}
        for phrase, count in phrase_counts.items()
        if count > 1
    ]

    normalized = " ".join(words)
    filler_counts: Counter[str] = Counter()
    occupied = [False] * len(words)
    for phrase in FILLER_PHRASES:
        phrase_words = phrase.split()
        size = len(phrase_words)
        for index in range(len(words) - size + 1):
            if words[index:index + size] == phrase_words:
                filler_counts[phrase] += 1
                occupied[index:index + size] = [True] * size
    for index, word in enumerate(words):
        if not occupied[index] and word in FILLER_WORDS:
            filler_counts[word] += 1

    corrections = {
        cue: len(re.findall(rf"(?<![а-я]){re.escape(cue)}(?![а-я])", normalized))
        for cue in CORRECTION_CUES
    }
    corrections = {cue: count for cue, count in corrections.items() if count}
    unfinished = bool(words and words[-1] in UNFINISHED_ENDINGS)
    unfinished = unfinished or bool(re.search(r"(?:--|…|\.\.\.)\s*$", text.strip()))

    lexical_diversity = None
    if len(words) >= MIN_LEXICAL_WORDS:
        lexical_diversity = round(len(counts) / len(words), 4)

    return {
        "word_count": len(words),
        "unique_word_count": len(counts),
        "lexical_diversity": lexical_diversity,
        "lexical_diversity_min_words": MIN_LEXICAL_WORDS,
        "word_repetitions": {
            "count": sum(item["extra_occurrences"] for item in repetitions),
            "items": repetitions,
        },
        "phrase_repetitions": {
            "count": sum(item["extra_occurrences"] for item in repeated_phrases),
            "items": repeated_phrases,
        },
        "self_corrections": {
            "count": sum(corrections.values()),
            "markers": corrections,
        },
        "fillers": {
            "count": sum(filler_counts.values()),
            "items": dict(filler_counts),
        },
        "unfinished_utterances": {
            "count": int(unfinished),
            "detected": unfinished,
        },
    }


def analyze_wav(path: str | Path) -> dict[str, Any]:
    """Извлечь длительность, начало речи и внутренние паузы из PCM WAV."""
    try:
        with wave.open(str(path), "rb") as source:
            channels = source.getnchannels()
            sample_rate = source.getframerate()
            sample_width = source.getsampwidth()
            frame_count = source.getnframes()
            raw = source.readframes(frame_count)
    except (OSError, EOFError, wave.Error):
        return {}

    if not raw or sample_rate <= 0 or sample_width not in {1, 2, 4}:
        return {}
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[sample_width]
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if sample_width == 1:
        samples -= 128.0
    if channels > 1:
        samples = samples[: len(samples) // channels * channels]
        samples = samples.reshape(-1, channels).mean(axis=1)
    peak_value = float(2 ** (sample_width * 8 - 1))
    samples /= peak_value
    duration = len(samples) / sample_rate
    if len(samples) < FRAME_LENGTH:
        samples = np.pad(samples, (0, FRAME_LENGTH - len(samples)))

    starts = np.arange(0, len(samples) - FRAME_LENGTH + 1, HOP_LENGTH)
    rms = np.sqrt(
        np.asarray([
            np.mean(samples[start:start + FRAME_LENGTH] ** 2)
            for start in starts
        ])
    )
    if not rms.size or float(np.max(rms)) <= 0:
        return {
            "duration_seconds": round(duration, 3),
            "active_speech_seconds": 0.0,
            "time_to_first_response_seconds": None,
            "pause_count": 0,
            "total_pause_seconds": 0.0,
        }

    threshold = RELATIVE_SILENCE_THRESHOLD * float(np.max(rms))
    speech = rms >= threshold
    changes = np.diff(np.concatenate(([False], speech, [False])).astype(int))
    speech_starts = np.flatnonzero(changes == 1)
    speech_ends = np.flatnonzero(changes == -1)
    speech_durations = (speech_ends - speech_starts) * HOP_LENGTH / sample_rate
    pause_durations = (
        (speech_starts[1:] - speech_ends[:-1]) * HOP_LENGTH / sample_rate
        if len(speech_starts) > 1
        else np.asarray([], dtype=float)
    )
    pause_durations = pause_durations[pause_durations >= MIN_PAUSE_SECONDS]
    first_response = (
        float(speech_starts[0] * HOP_LENGTH / sample_rate)
        if len(speech_starts)
        else None
    )
    return {
        "duration_seconds": round(duration, 3),
        "active_speech_seconds": round(float(np.sum(speech_durations)), 3),
        "time_to_first_response_seconds": (
            round(first_response, 3) if first_response is not None else None
        ),
        "pause_count": int(len(pause_durations)),
        "total_pause_seconds": round(float(np.sum(pause_durations)), 3),
        "pause_threshold": {
            "relative_rms": RELATIVE_SILENCE_THRESHOLD,
            "minimum_seconds": MIN_PAUSE_SECONDS,
        },
    }


def build_speech_metrics(
    text: str,
    acoustic_parts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Объединить текстовые метрики и акустику одного или нескольких WAV."""
    metrics = analyze_text(text)
    parts = [part for part in acoustic_parts or [] if part]
    duration = sum(float(part.get("duration_seconds") or 0) for part in parts)
    active = sum(float(part.get("active_speech_seconds") or 0) for part in parts)
    word_count = int(metrics["word_count"])
    metrics.update(
        {
            "duration_seconds": round(duration, 3) if parts else None,
            "active_speech_seconds": round(active, 3) if parts else None,
            "words_per_minute": (
                round(word_count * 60 / duration, 2) if duration > 0 else None
            ),
            "words_per_active_minute": (
                round(word_count * 60 / active, 2) if active > 0 else None
            ),
            "time_to_first_response_seconds": (
                parts[0].get("time_to_first_response_seconds") if parts else None
            ),
            "pause_count": sum(int(part.get("pause_count") or 0) for part in parts),
            "total_pause_seconds": round(
                sum(float(part.get("total_pause_seconds") or 0) for part in parts),
                3,
            ) if parts else None,
            "acoustic_part_count": len(parts),
        }
    )
    return metrics


def summarize_speech_metrics(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Сформировать общие показатели по всем записанным ответам MoCA."""
    transcripts = [str(task.get("transcript") or "") for task in tasks]
    textual = analyze_text(" ".join(transcripts))
    metrics = [
        task.get("speech_metrics", {})
        for task in tasks
        if isinstance(task.get("speech_metrics"), dict)
    ]
    durations = [item.get("duration_seconds") for item in metrics]
    has_acoustics = any(value is not None for value in durations)
    duration = sum(float(value or 0) for value in durations)
    active = sum(float(item.get("active_speech_seconds") or 0) for item in metrics)
    words = int(textual["word_count"])
    textual.update(
        {
            "duration_seconds": round(duration, 3) if has_acoustics else None,
            "active_speech_seconds": round(active, 3) if has_acoustics else None,
            "words_per_minute": (
                round(words * 60 / duration, 2) if duration > 0 else None
            ),
            "words_per_active_minute": (
                round(words * 60 / active, 2) if active > 0 else None
            ),
            "pause_count": sum(int(item.get("pause_count") or 0) for item in metrics),
            "total_pause_seconds": (
                round(sum(float(item.get("total_pause_seconds") or 0) for item in metrics), 3)
                if has_acoustics
                else None
            ),
            "average_time_to_first_response_seconds": _average_available(
                item.get("time_to_first_response_seconds") for item in metrics
            ),
            "task_count": len(tasks),
        }
    )
    return textual


def _average_available(values: Any) -> float | None:
    """Усреднить только реально измеренные значения."""
    available = [float(value) for value in values if value is not None]
    if not available:
        return None
    return round(sum(available) / len(available), 3)

"""Разбиение длинного аудио на речевые реплики по паузам."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


# CONFIG ---------------------------------------------------------------------
FRAME_SECONDS = 0.03
HOP_SECONDS = 0.01
NOISE_PERCENTILE = 25.0
NOISE_MULTIPLIER = 4.0
MIN_RMS_THRESHOLD = 0.0006
SPLIT_SILENCE_SECONDS = 0.70
PADDING_SECONDS = 0.25
MIN_CHUNK_SECONDS = 0.20
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeechChunk:
    """Речевая реплика в оперативной памяти и её границы."""

    audio: np.ndarray
    start: float
    end: float


def _frame_rms(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    """Рассчитать RMS последовательных перекрывающихся окон."""
    frame_size = max(1, round(FRAME_SECONDS * sample_rate))
    hop_size = max(1, round(HOP_SECONDS * sample_rate))
    last_start = max(1, len(audio) - frame_size + 1)
    values = [
        float(
            np.sqrt(
                np.mean(np.square(audio[start:start + frame_size])) + 1e-12
            )
        )
        for start in range(0, last_start, hop_size)
    ]
    return np.asarray(values, dtype=np.float32), hop_size


def detect_speech_intervals(
    audio: np.ndarray,
    sample_rate: int,
) -> tuple[list[tuple[float, float]], float]:
    """Объединить активные окна в реплики, разделённые длинными паузами."""
    if not audio.size:
        return [], MIN_RMS_THRESHOLD
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    rms, hop_size = _frame_rms(audio, sample_rate)
    noise_rms = float(np.percentile(rms, NOISE_PERCENTILE))
    threshold = max(MIN_RMS_THRESHOLD, noise_rms * NOISE_MULTIPLIER)
    active = np.flatnonzero(rms >= threshold)
    if not active.size:
        return [], threshold

    max_gap = max(1, round(SPLIT_SILENCE_SECONDS * sample_rate / hop_size))
    groups: list[list[int]] = [[int(active[0])]]
    for index in active[1:]:
        if int(index) - groups[-1][-1] > max_gap:
            groups.append([int(index)])
        else:
            groups[-1].append(int(index))

    duration = len(audio) / sample_rate
    intervals = []
    for group in groups:
        start = max(0.0, group[0] * hop_size / sample_rate - PADDING_SECONDS)
        end = min(
            duration,
            group[-1] * hop_size / sample_rate + FRAME_SECONDS + PADDING_SECONDS,
        )
        if end - start >= MIN_CHUNK_SECONDS:
            intervals.append((start, end))
    return intervals, threshold


def split_audio(
    audio: np.ndarray,
    sample_rate: int,
) -> tuple[list[SpeechChunk], float]:
    """Найти речевые реплики и оставить их массивы в оперативной памяти."""
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    intervals, threshold = detect_speech_intervals(audio, sample_rate)

    chunks = []
    for start, end in intervals:
        first = round(start * sample_rate)
        last = round(end * sample_rate)
        chunks.append(
            SpeechChunk(
                audio=audio[first:last].copy(),
                start=start,
                end=end,
            )
        )
    return chunks, threshold


def split_audio_file(
    audio_path: Path,
) -> tuple[list[SpeechChunk], float]:
    """Прочитать аудиофайл и вернуть речевые реплики без записи на диск."""
    audio, sample_rate = sf.read(audio_path, dtype="float32")
    return split_audio(audio, sample_rate)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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


def analyze_audio(audio_path: str) -> AudioAnalysisResult:
    """Analyse a WAV file and return speech biomarker metrics.

    This is a **stub** implementation.  Replace the body with real
    analysis code once the external module is available.

    The function is intentionally synchronous — callers should use
    ``asyncio.to_thread(analyze_audio, path)`` from async context.

    Parameters
    ----------
    audio_path:
        Path to a WAV file recorded from the microphone.
    """
    # TODO: подставить реальный код аудио-анализа от разработчика.
    # Пример вызова:
    #   from external_screening_lib import audio as ext_audio
    #   return ext_audio.run(audio_path)

    if not audio_path:
        return AudioAnalysisResult(
            notes="Акустические маркеры недоступны: путь к аудио не задан.",
        )

    # The algorithm is not implemented: never return fabricated measurements.
    return AudioAnalysisResult(
        notes="Акустические речевые маркеры недоступны: алгоритм не реализован.",
    )

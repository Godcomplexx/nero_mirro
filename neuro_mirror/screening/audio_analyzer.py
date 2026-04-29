from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AudioAnalysisResult:
    """Result of audio analysis for screening."""

    speech_score: float = 0.0           # 0.0-1.0  (clarity / coherence)
    speech_rate_wpm: float = 0.0        # words per minute
    pause_ratio: float = 0.0           # fraction of silence
    reaction_ms: int = 0               # time to first utterance
    pitch_variability: float = 0.0     # tonal variability
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
            notes="STUB: путь к аудио-файлу не задан.",
        )

    # Stub: имитируем базовый результат
    return AudioAnalysisResult(
        speech_score=0.72,
        speech_rate_wpm=120.0,
        pause_ratio=0.15,
        reaction_ms=650,
        pitch_variability=0.40,
        biomarker_flags=[],
        transcript="",
        notes="STUB: подставить реальный код аудио-анализа.",
    )

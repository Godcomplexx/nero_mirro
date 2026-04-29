from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class VideoAnalysisResult:
    """Result of video-frame analysis for screening."""

    attention_score: float = 0.0        # 0.0-1.0
    gaze_stability: float = 0.0         # 0.0-1.0
    micro_expression_flags: list[str] = field(default_factory=list)
    face_detected: bool = False
    face_count: int = 0
    notes: str = ""


def analyze_frames(frames: list[bytes]) -> VideoAnalysisResult:
    """Analyse raw image frames and return screening metrics.

    This is a **stub** implementation.  Replace the body with real
    analysis code once the external module is available.

    The function is intentionally synchronous — callers should use
    ``asyncio.to_thread(analyze_frames, frames)`` from async context.

    Parameters
    ----------
    frames:
        List of raw image bytes (e.g. PNG/JPEG).  At least one frame
        is expected; more frames improve accuracy.
    """
    # TODO: подставить реальный код видео-анализа от разработчика.
    # Пример вызова:
    #   from external_screening_lib import video as ext_video
    #   return ext_video.run(frames)

    if not frames:
        return VideoAnalysisResult(
            notes="STUB: нет кадров для анализа.",
        )

    # Stub: имитируем базовый результат
    return VideoAnalysisResult(
        attention_score=0.75,
        gaze_stability=0.70,
        micro_expression_flags=[],
        face_detected=True,
        face_count=1,
        notes="STUB: подставить реальный код видео-анализа.",
    )

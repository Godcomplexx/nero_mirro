from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class VideoAnalysisResult:
    """Result of video-frame analysis for screening."""

    attention_score: Optional[float] = None
    gaze_stability: Optional[float] = None
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
            notes="Видео-маркеры недоступны: кадры для анализа не получены.",
        )

    # The algorithm is not implemented: never return fabricated measurements.
    return VideoAnalysisResult(
        notes="Видео-маркеры внимания и взгляда недоступны: алгоритм не реализован.",
    )

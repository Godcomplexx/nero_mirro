"""Показатели видеопотока для скрининга.

Присутствие лица в кадре определяется здесь по-настоящему: тем же детектором,
которым проверяются условия сессии. Это нужно, чтобы отличить отсутствие
человека перед камерой от неудачного замера.

Чего здесь нет и не выдумывается: оценка внимания, устойчивость взгляда и
признаки мимики. Для них нужна утверждённая методика; подставить вместо неё
собственную формулу нельзя — числа уйдут специалисту и будут выглядеть
измерением. Поля остаются пустыми, а причина записывается в примечание.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from neuro_mirror.screening.session_check import analyze_frame_conditions

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VideoAnalysisResult:
    """Result of video-frame analysis for screening."""

    attention_score: Optional[float] = None
    gaze_stability: Optional[float] = None
    micro_expression_flags: list[str] = field(default_factory=list)
    face_detected: bool = False
    face_count: int = 0
    notes: str = ""
    # Доля кадра, занятая лицом, и признак достаточной близости: по ним видно,
    # годится ли кадр для измерений вообще.
    face_ratio: float = 0.0
    face_close_enough: bool = False
    detector_available: bool = True


MISSING_NOTE = (
    "Оценка внимания, устойчивость взгляда и признаки мимики не "
    "рассчитываются: методика не утверждена."
)


def analyze_frames(frames: list[bytes]) -> VideoAnalysisResult:
    """Измерить присутствие лица по кадрам.

    Берётся последний кадр: он ближе всего к моменту замера. Перебирать все
    кадры незачем — присутствие человека за доли секунды не меняется.

    Функция намеренно синхронная — вызывающий использует
    ``asyncio.to_thread(analyze_frames, frames)``.
    """
    usable = [frame for frame in frames if frame]
    if not usable:
        return VideoAnalysisResult(
            notes="Видеокадры не получены: присутствие лица не определено.",
        )

    try:
        conditions = analyze_frame_conditions(usable[-1])
    except Exception as exc:  # noqa: BLE001 — сбой разбора кадра не роняет скрининг
        logger.warning("video_analyzer: не удалось разобрать кадр: %s", exc)
        return VideoAnalysisResult(
            notes="Кадр не удалось разобрать: присутствие лица не определено.",
        )

    detector_available = bool(conditions.get("detector_available", True))
    return VideoAnalysisResult(
        face_detected=bool(conditions.get("face_detected")),
        face_count=int(conditions.get("face_count") or 0),
        face_ratio=float(conditions.get("face_ratio") or 0.0),
        face_close_enough=bool(conditions.get("face_close_enough")),
        detector_available=detector_available,
        notes=(
            MISSING_NOTE
            if detector_available
            else "Детектор лиц недоступен; " + MISSING_NOTE
        ),
    )

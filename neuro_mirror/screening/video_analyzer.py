"""Разбор видеокадров для скрининга.

Техническое задание требует от видеоанализа трёх вещей: контроль присутствия
лица в кадре, бесконтактную оценку частоты сердечных сокращений по видео при
наличии алгоритма и фиксацию событий низкого качества с учётом их при оценке
достоверности. Здесь делается первое и третье; частота сердечных сокращений
считается отдельным процессом видеоанализа и приходит оттуда.

Оценки внимания, устойчивости взгляда и признаков мимики здесь нет. Такие
поля оставались от прежней заглушки, техническое задание их не требует, а
алгоритма для них не существует — пустое поле создавало впечатление
недоделки там, где её нет.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from neuro_mirror.screening.session_check import analyze_frame_conditions

logger = logging.getLogger(__name__)

# Доля кадра, ниже которой лицо считается слишком мелким для измерений.
MIN_FACE_RATIO = 0.04

# Коды событий низкого качества. Передаются дальше как есть, чтобы отчёт мог
# объяснить человеку, почему измерение ограничено.
QUALITY_NO_FRAMES = "no_frames"
QUALITY_UNREADABLE = "unreadable_frame"
QUALITY_NO_FACE = "no_face"
QUALITY_FACE_TOO_SMALL = "face_too_small"
QUALITY_NO_DETECTOR = "detector_unavailable"

QUALITY_LABELS: dict[str, str] = {
    QUALITY_NO_FRAMES: "Кадры с камеры не получены.",
    QUALITY_UNREADABLE: "Кадр не удалось разобрать.",
    QUALITY_NO_FACE: "Лицо в кадре не обнаружено.",
    QUALITY_FACE_TOO_SMALL: "Лицо занимает малую часть кадра: подойдите ближе.",
    QUALITY_NO_DETECTOR: "Детектор лиц недоступен.",
}


@dataclass(slots=True)
class VideoAnalysisResult:
    """Что измерено по кадрам."""

    face_detected: bool = False
    face_count: int = 0
    face_ratio: float = 0.0
    face_close_enough: bool = False
    detector_available: bool = True
    # События низкого качества: по ним видно, насколько измерению можно верить.
    quality_issues: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def usable(self) -> bool:
        """Годится ли кадр для измерений по видео."""
        return self.face_detected and self.face_close_enough and not self.quality_issues


def describe_quality(issues: list[str]) -> str:
    """Человеческое описание событий низкого качества."""
    return " ".join(QUALITY_LABELS.get(code, code) for code in issues)


def analyze_frames(frames: list[bytes]) -> VideoAnalysisResult:
    """Измерить присутствие лица и зафиксировать события низкого качества.

    Берётся последний кадр: он ближе всего к моменту замера. Перебирать все
    кадры незачем — присутствие человека за доли секунды не меняется.

    Функция намеренно синхронная — вызывающий использует
    ``asyncio.to_thread(analyze_frames, frames)``.
    """
    usable_frames = [frame for frame in frames if frame]
    if not usable_frames:
        issues = [QUALITY_NO_FRAMES]
        return VideoAnalysisResult(quality_issues=issues, notes=describe_quality(issues))

    try:
        conditions = analyze_frame_conditions(usable_frames[-1])
    except Exception as exc:  # noqa: BLE001 — сбой разбора кадра не роняет скрининг
        logger.warning("video_analyzer: не удалось разобрать кадр: %s", exc)
        issues = [QUALITY_UNREADABLE]
        return VideoAnalysisResult(quality_issues=issues, notes=describe_quality(issues))

    detector_available = bool(conditions.get("detector_available", True))
    face_detected = bool(conditions.get("face_detected"))
    face_ratio = float(conditions.get("face_ratio") or 0.0)
    face_close_enough = bool(conditions.get("face_close_enough"))

    issues: list[str] = []
    if not detector_available:
        issues.append(QUALITY_NO_DETECTOR)
    elif not face_detected:
        issues.append(QUALITY_NO_FACE)
    elif not face_close_enough or face_ratio < MIN_FACE_RATIO:
        issues.append(QUALITY_FACE_TOO_SMALL)

    return VideoAnalysisResult(
        face_detected=face_detected,
        face_count=int(conditions.get("face_count") or 0),
        face_ratio=face_ratio,
        face_close_enough=face_close_enough,
        detector_available=detector_available,
        quality_issues=issues,
        notes=describe_quality(issues),
    )

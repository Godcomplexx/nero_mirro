from __future__ import annotations

from dataclasses import dataclass, field

from neuro_mirror.screening.video_analyzer import VideoAnalysisResult
from neuro_mirror.screening.audio_analyzer import AudioAnalysisResult


@dataclass(slots=True)
class ScreeningScore:
    """Aggregated screening score with risk assessment."""

    overall_score: float = 0.0          # 0.0-1.0
    risk_level: str = "medium"          # "low" | "medium" | "high"
    domain_scores: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    notes: str = ""


# Domain weights for overall score calculation
_DOMAIN_WEIGHTS: dict[str, float] = {
    "attention": 0.25,
    "gaze": 0.15,
    "speech": 0.25,
    "reaction": 0.15,
    "pitch": 0.10,
    "pause": 0.10,
}


def _normalise_reaction(reaction_ms: int) -> float:
    """Convert reaction time in ms to a 0-1 score (lower is better)."""
    if reaction_ms <= 0:
        return 0.5  # unknown
    if reaction_ms <= 300:
        return 1.0
    if reaction_ms >= 2000:
        return 0.0
    # Linear interpolation 300..2000 -> 1.0..0.0
    return max(0.0, 1.0 - (reaction_ms - 300) / 1700)


def _invert_ratio(ratio: float) -> float:
    """Convert a 0-1 ratio where lower is better to a score where higher is better."""
    return max(0.0, min(1.0, 1.0 - ratio))


def compute_screening_score(
    video: VideoAnalysisResult,
    audio: AudioAnalysisResult,
) -> ScreeningScore:
    """Compute an aggregated screening score from video and audio results.

    Parameters
    ----------
    video:
        Result from ``analyze_frames``.
    audio:
        Result from ``analyze_audio``.

    Returns
    -------
    ScreeningScore with overall_score, risk_level, domain breakdowns
    and recommendations.
    """
    domain_scores: dict[str, float] = {
        "attention": max(0.0, min(1.0, video.attention_score)),
        "gaze": max(0.0, min(1.0, video.gaze_stability)),
        "speech": max(0.0, min(1.0, audio.speech_score)),
        "reaction": _normalise_reaction(audio.reaction_ms),
        "pitch": max(0.0, min(1.0, audio.pitch_variability)),
        "pause": _invert_ratio(audio.pause_ratio),
    }

    # Weighted average
    total_weight = sum(_DOMAIN_WEIGHTS.values())
    overall = sum(
        domain_scores.get(domain, 0.0) * weight
        for domain, weight in _DOMAIN_WEIGHTS.items()
    ) / total_weight if total_weight > 0 else 0.0

    overall = round(overall, 3)

    # Risk level thresholds
    if overall >= 0.7:
        risk_level = "low"
    elif overall >= 0.4:
        risk_level = "medium"
    else:
        risk_level = "high"

    # Recommendations
    recommendations: list[str] = []
    if risk_level == "high":
        recommendations.append("Рекомендуется консультация специалиста.")
        recommendations.append("Повторить скрининг через 3 дня.")
    elif risk_level == "medium":
        recommendations.append("Повторить скрининг через неделю.")
        if domain_scores.get("speech", 1.0) < 0.5:
            recommendations.append("Обратить внимание на речевые показатели.")
        if domain_scores.get("attention", 1.0) < 0.5:
            recommendations.append("Обратить внимание на показатели внимания.")
    else:
        recommendations.append("Показатели в норме. Следующий скрининг через месяц.")

    # Biomarker notes
    notes_parts: list[str] = []
    if video.micro_expression_flags:
        notes_parts.append(f"Микро-выражения: {', '.join(video.micro_expression_flags)}.")
    if audio.biomarker_flags:
        notes_parts.append(f"Речевые биомаркеры: {', '.join(audio.biomarker_flags)}.")

    return ScreeningScore(
        overall_score=overall,
        risk_level=risk_level,
        domain_scores=domain_scores,
        recommendations=recommendations,
        notes=" ".join(notes_parts),
    )

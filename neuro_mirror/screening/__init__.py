"""Разбор записей скрининга.

Измеримое измеряется: по аудиозаписи считаются задержка ответа, паузы и темп
речи, по кадрам определяется присутствие лица. Сводные клинические оценки —
оценка речи, изменчивость высоты голоса, внимание, устойчивость взгляда —
остаются пустыми: для них нужна утверждённая методика, и подставлять вместо
неё собственную формулу нельзя, числа уходят специалисту.
"""

from neuro_mirror.screening.video_analyzer import VideoAnalysisResult, analyze_frames
from neuro_mirror.screening.audio_analyzer import AudioAnalysisResult, analyze_audio
from neuro_mirror.screening.scoring import ScreeningScore, compute_screening_score

__all__ = [
    "VideoAnalysisResult",
    "analyze_frames",
    "AudioAnalysisResult",
    "analyze_audio",
    "ScreeningScore",
    "compute_screening_score",
]

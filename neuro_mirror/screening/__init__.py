"""Разбор записей скрининга.

По аудиозаписи считаются задержка ответа, доля пауз и темп речи. По кадрам
определяется присутствие лица и фиксируются события низкого качества —
по ним видно, насколько измерению можно верить.

Это измерения, а не клиническая оценка. Сводного показателя состояния здесь
нет: он требует утверждённой методики, а подставлять вместо неё собственные
веса и пороги нельзя — результат уйдёт специалисту и будет выглядеть
измерением.
"""

from neuro_mirror.screening.video_analyzer import VideoAnalysisResult, analyze_frames
from neuro_mirror.screening.audio_analyzer import AudioAnalysisResult, analyze_audio

__all__ = [
    "VideoAnalysisResult",
    "analyze_frames",
    "AudioAnalysisResult",
    "analyze_audio",
]

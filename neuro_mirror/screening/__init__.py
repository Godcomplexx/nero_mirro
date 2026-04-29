"""Screening analysis adapters.

This package provides a thin adapter layer around the external screening
analysis code.  When the real analysis modules are available, replace the
stub function bodies in ``video_analyzer.py`` and ``audio_analyzer.py``.
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

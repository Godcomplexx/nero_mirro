from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from neuro_mirror.utils.speech_split import (
    detect_speech_intervals,
    split_audio_file,
)


class SpeechSplitTest(unittest.TestCase):
    def test_detects_two_utterances_separated_by_pause(self) -> None:
        sample_rate = 16_000
        silence = np.zeros(sample_rate, dtype=np.float32)
        tone = np.full(sample_rate // 2, 0.03, dtype=np.float32)
        audio = np.concatenate((silence, tone, silence, tone, silence))

        intervals, threshold = detect_speech_intervals(audio, sample_rate)

        self.assertEqual(len(intervals), 2)
        self.assertGreaterEqual(threshold, 0.0006)
        self.assertLess(intervals[0][0], 1.0)
        self.assertGreater(intervals[0][1], 1.5)
        self.assertLess(intervals[1][0], 2.5)
        self.assertGreater(intervals[1][1], 3.0)

    def test_silent_audio_produces_no_chunks(self) -> None:
        sample_rate = 16_000
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            audio_path = root / "silence.wav"
            sf.write(audio_path, np.zeros(sample_rate), sample_rate)

            chunks, _ = split_audio_file(audio_path)

        self.assertEqual(chunks, [])

    def test_chunks_are_kept_in_memory(self) -> None:
        sample_rate = 16_000
        silence = np.zeros(sample_rate, dtype=np.float32)
        speech = np.full(sample_rate, 0.03, dtype=np.float32)
        audio = np.concatenate((silence, speech, silence))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            audio_path = root / "speech.wav"
            sf.write(audio_path, audio, sample_rate)

            chunks, _ = split_audio_file(audio_path)

            self.assertEqual([path.name for path in root.iterdir()], ["speech.wav"])
        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(chunks[0].audio, np.ndarray)


if __name__ == "__main__":
    unittest.main()

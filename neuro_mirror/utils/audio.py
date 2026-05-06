"""Shared audio recording utility."""
from __future__ import annotations

import os
import tempfile
import threading
import wave

import numpy as np

try:
    import sounddevice as sd  # type: ignore
except Exception:
    sd = None


class VoiceRecorder:
    """Records audio from the default input device into a WAV file.

    Used by both ``MicrophonePlugin`` (interactive recording) and
    ``VoiceTestPlugin`` (timed screening recording).
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        channels: int,
        max_seconds: float,
        silence_threshold: float = 0.012,
        silence_duration: float = 1.8,
        min_speech_duration: float = 0.4,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_seconds = max_seconds
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.min_speech_duration = min_speech_duration
        self._stream = None
        self._wave_file: wave.Wave_write | None = None
        self._file_path = ""
        self._lock = threading.Lock()
        self._captured_frames = 0

    @property
    def available(self) -> bool:
        return sd is not None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> str:
        if sd is None:
            raise RuntimeError("sounddevice не установлен")
        if self._stream is not None:
            raise RuntimeError("запись уже выполняется")

        fd, file_path = tempfile.mkstemp(prefix="neuro_mirror_", suffix=".wav")
        os.close(fd)
        self._file_path = file_path
        self._captured_frames = 0

        wave_file = wave.open(file_path, "wb")
        wave_file.setnchannels(self.channels)
        wave_file.setsampwidth(2)
        wave_file.setframerate(self.sample_rate)
        self._wave_file = wave_file
        max_frames = int(self.sample_rate * self.max_seconds)
        min_speech_frames = int(self.sample_rate * self.min_speech_duration)
        silence_stop_frames = int(self.sample_rate * self.silence_duration)

        # Mutable state for VAD inside the callback
        vad = {"speech_frames": 0, "silence_frames": 0}

        def callback(indata, frames, _time, status) -> None:
            if status:
                return
            pcm = (np.clip(indata, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            rms = float(np.sqrt(np.mean(indata ** 2)))

            with self._lock:
                if self._wave_file is not None:
                    self._wave_file.writeframes(pcm)
                    self._captured_frames += frames

                if rms >= self.silence_threshold:
                    vad["speech_frames"] += frames
                    vad["silence_frames"] = 0
                else:
                    vad["silence_frames"] += frames

                speech_started = vad["speech_frames"] >= min_speech_frames
                silence_long_enough = vad["silence_frames"] >= silence_stop_frames

                if self._captured_frames >= max_frames:
                    raise sd.CallbackStop()
                # Stop early only after user has spoken and then gone silent
                if speech_started and silence_long_enough:
                    raise sd.CallbackStop()

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        return file_path

    def stop(self) -> str:
        if self._stream is None:
            return ""

        self._stream.stop()
        self._stream.close()
        self._stream = None

        with self._lock:
            if self._wave_file is not None:
                self._wave_file.close()
                self._wave_file = None

        file_path = self._file_path
        self._file_path = ""
        return file_path

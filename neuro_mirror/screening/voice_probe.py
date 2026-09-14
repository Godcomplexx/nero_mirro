"""Readiness probe for the microphone the test itself will use.

The browser can hear the patient through ``getUserMedia`` while the recorder
that captures MoCA and HADS answers — :class:`VoiceRecorder`, driven by
``sounddevice`` in the server process — cannot: the device may be missing,
held by another program, or open but silent. A probe that only measures level
in the browser therefore proves nothing about the path that matters.

This module records a short sample through that same recorder and reports
whether it captured audible speech, so the check fails before the test starts
rather than in the middle of it.
"""
from __future__ import annotations

import contextlib
import math
import wave
from dataclasses import dataclass
from pathlib import Path

# Spoken during the probe. Short, unambiguous, and recognisable by the speech
# model, so one utterance validates recording and recognition together.
PROBE_PHRASE = "раз, два, три"
PROBE_SECONDS = 4.0

# Peak level below this means the recorder produced silence: a device that is
# open but delivering nothing sounds exactly like a patient who said nothing.
SILENCE_PEAK = 0.012
# Digits the transcript should contain for recognition to count as confirmed.
PROBE_TOKENS = ("раз", "один", "два", "две", "три")


@dataclass(frozen=True)
class VoiceProbeResult:
    ok: bool
    state: str  # "ok" | "warn" | "fail"
    reason: str
    message: str
    peak_level: float | None = None
    transcript: str = ""


def measure_peak_level(path: str | Path) -> float | None:
    """Peak amplitude of a 16-bit WAV, normalised to 0..1."""
    with contextlib.suppress(OSError, wave.Error, ValueError):
        with wave.open(str(path), "rb") as handle:
            if handle.getsampwidth() != 2:
                return None
            frames = handle.readframes(handle.getnframes())
        if not frames:
            return 0.0
        peak = 0
        for index in range(0, len(frames) - 1, 2):
            sample = int.from_bytes(frames[index:index + 2], "little", signed=True)
            peak = max(peak, abs(sample))
        return round(peak / 32768.0, 5)
    return None


def evaluate_probe(
    *,
    recorded: bool,
    peak_level: float | None,
    transcript: str,
    failure_reason: str = "",
) -> VoiceProbeResult:
    """Turn a recording attempt into a verdict the interface can show."""
    if not recorded:
        reason = failure_reason or "unavailable"
        messages = {
            "no_device": (
                "Микрофон не найден. Подключите его и разрешите доступ "
                "в настройках Windows."
            ),
            "busy": (
                "Микрофон занят другой программой. Закройте её и повторите "
                "проверку."
            ),
        }
        return VoiceProbeResult(
            ok=False,
            state="fail",
            reason=reason,
            message=messages.get(reason, "Не удалось записать пробу голоса."),
        )

    if peak_level is not None and peak_level < SILENCE_PEAK:
        return VoiceProbeResult(
            ok=False,
            state="fail",
            reason="silence",
            message=(
                f"Запись идёт, но звука нет. Проверьте, что говорите в нужный "
                f"микрофон и он не выключен, затем произнесите «{PROBE_PHRASE}» снова."
            ),
            peak_level=peak_level,
            transcript=transcript,
        )

    normalized = transcript.lower().replace("ё", "е")
    if not normalized.strip():
        return VoiceProbeResult(
            ok=False,
            state="warn",
            reason="not_recognized",
            message=(
                "Микрофон слышно, но речь не распознана. Говорите чётче и "
                "громче — иначе ответы в тесте не будут засчитаны."
            ),
            peak_level=peak_level,
            transcript=transcript,
        )

    if not any(token in normalized for token in PROBE_TOKENS):
        return VoiceProbeResult(
            ok=False,
            state="warn",
            reason="unexpected_phrase",
            message=(
                f"Распознано «{transcript.strip()}». Произнесите именно "
                f"«{PROBE_PHRASE}» и повторите проверку."
            ),
            peak_level=peak_level,
            transcript=transcript,
        )

    return VoiceProbeResult(
        ok=True,
        state="ok",
        reason="confirmed",
        message="Микрофон работает, речь распознаётся.",
        peak_level=peak_level,
        transcript=transcript,
    )


def is_silent(peak_level: float | None) -> bool:
    return peak_level is not None and not math.isnan(peak_level) and peak_level < SILENCE_PEAK

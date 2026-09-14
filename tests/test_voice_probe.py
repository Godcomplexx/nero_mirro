"""Microphone readiness probe: the check must exercise the real record path."""
from __future__ import annotations

import struct
import wave

from neuro_mirror.screening.voice_probe import (
    PROBE_PHRASE,
    SILENCE_PEAK,
    evaluate_probe,
    is_silent,
    measure_peak_level,
)


def _wav(path, samples, sample_rate=16000):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))
    return str(path)


# ── Level measurement ──────────────────────────────────────────────────────────

def test_peak_level_of_silence_is_zero(tmp_path):
    path = _wav(tmp_path / "silence.wav", [0] * 1600)
    assert measure_peak_level(path) == 0.0


def test_peak_level_reflects_the_loudest_sample(tmp_path):
    path = _wav(tmp_path / "speech.wav", [0, 1000, -16384, 500])
    assert measure_peak_level(path) == 0.5


def test_peak_level_of_a_missing_file_is_unknown(tmp_path):
    assert measure_peak_level(tmp_path / "nope.wav") is None


def test_peak_level_of_a_non_wav_file_is_unknown(tmp_path):
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not a wav at all")
    assert measure_peak_level(path) is None


# ── Verdicts ───────────────────────────────────────────────────────────────────

def test_missing_device_fails_with_actionable_message():
    result = evaluate_probe(
        recorded=False, peak_level=None, transcript="", failure_reason="no_device",
    )
    assert result.ok is False
    assert result.state == "fail"
    assert result.reason == "no_device"
    assert "Подключите" in result.message


def test_busy_device_is_reported_separately_from_a_missing_one():
    """The two faults need different advice, so they must not be merged."""
    result = evaluate_probe(
        recorded=False, peak_level=None, transcript="", failure_reason="busy",
    )
    assert result.state == "fail"
    assert result.reason == "busy"
    assert "занят" in result.message


def test_open_but_silent_device_fails():
    """A device that records nothing sounds exactly like a silent patient."""
    result = evaluate_probe(recorded=True, peak_level=0.0, transcript="")
    assert result.ok is False
    assert result.state == "fail"
    assert result.reason == "silence"


def test_audible_but_unrecognised_speech_warns():
    result = evaluate_probe(recorded=True, peak_level=0.3, transcript="")
    assert result.ok is False
    assert result.state == "warn"
    assert result.reason == "not_recognized"


def test_wrong_phrase_warns_and_quotes_what_was_heard():
    result = evaluate_probe(recorded=True, peak_level=0.3, transcript="проверка связи")
    assert result.state == "warn"
    assert result.reason == "unexpected_phrase"
    assert "проверка связи" in result.message
    assert PROBE_PHRASE in result.message


def test_recognised_probe_phrase_passes():
    result = evaluate_probe(recorded=True, peak_level=0.3, transcript="раз два три")
    assert result.ok is True
    assert result.state == "ok"
    assert result.reason == "confirmed"


def test_digits_spoken_as_numerals_pass():
    result = evaluate_probe(recorded=True, peak_level=0.25, transcript="Один, два, три.")
    assert result.ok is True


def test_yo_is_normalised_before_matching():
    result = evaluate_probe(recorded=True, peak_level=0.25, transcript="трЁх раз")
    assert result.ok is True


def test_unknown_level_does_not_block_a_recognised_phrase():
    """A level we could not measure must not veto a clearly recognised answer."""
    result = evaluate_probe(recorded=True, peak_level=None, transcript="раз два три")
    assert result.ok is True


def test_is_silent_threshold():
    assert is_silent(0.0) is True
    assert is_silent(SILENCE_PEAK - 0.001) is True
    assert is_silent(SILENCE_PEAK + 0.001) is False
    assert is_silent(None) is False

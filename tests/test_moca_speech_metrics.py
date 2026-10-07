from __future__ import annotations

import wave
from unittest.mock import Mock

import numpy as np

from neuro_mirror.core.settings import Settings
from neuro_mirror.plugins.moca_test.plugin import MocaTask, MocaTestPlugin
from neuro_mirror.screening.moca_scoring import (
    score_moca_task,
    summarize_moca_tasks,
)
from neuro_mirror.screening.speech_metrics import analyze_text, analyze_wav


def test_text_metrics_count_repetitions_fillers_and_lexical_threshold() -> None:
    short = analyze_text("Ну дом дом, как бы сад")

    assert short["word_count"] == 6
    assert short["unique_word_count"] == 5
    assert short["lexical_diversity"] is None
    assert short["word_repetitions"]["count"] == 1
    assert short["fillers"]["count"] == 2

    long = analyze_text(" ".join(f"слово{index}" for index in range(20)))
    assert long["lexical_diversity"] == 1.0


def test_wav_metrics_detect_first_response_and_internal_pause(tmp_path) -> None:
    sample_rate = 16_000
    silence_1 = np.zeros(sample_rate, dtype=np.float32)
    speech_1 = np.full(sample_rate // 2, 0.5, dtype=np.float32)
    pause = np.zeros(int(sample_rate * 0.3), dtype=np.float32)
    speech_2 = np.full(sample_rate // 2, 0.5, dtype=np.float32)
    samples = np.concatenate((silence_1, speech_1, pause, speech_2))
    pcm = (samples * 32767).astype(np.int16)
    path = tmp_path / "answer.wav"
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(pcm.tobytes())

    metrics = analyze_wav(path)

    assert metrics["duration_seconds"] == 2.3
    assert 0.9 <= metrics["time_to_first_response_seconds"] <= 1.05
    assert metrics["pause_count"] == 1
    assert 0.2 <= metrics["total_pause_seconds"] <= 0.35


def test_every_task_gets_element_counts_and_specialized_analysis() -> None:
    memory = score_moca_task("memory_1", "лицо лицо дом бархат")
    assert memory["task_analysis"]["correct_elements"]["items"] == [
        "лицо",
        "бархат",
    ]
    assert memory["task_analysis"]["repeated_elements"]["items"] == ["лицо"]
    assert memory["task_analysis"]["extraneous_elements"]["items"] == ["дом"]

    fluency = score_moca_task(
        "language_fluency",
        "лампа лодка лампа дом Леонид",
    )
    fluency_data = fluency["task_analysis"]["fluency"]
    assert fluency_data["valid_words"] == ["лампа", "лодка"]
    assert fluency_data["repetitions"] == ["лампа"]
    assert fluency["task_analysis"]["extraneous_elements"]["items"] == [
        "дом",
        "леонид",
    ]

    abstraction = score_moca_task("abstraction_1", "Это транспорт")
    semantic = abstraction["task_analysis"]["semantic_features"]
    assert semantic["abstract_category_detected"] is True
    assert "transport" in semantic["matched_concepts"]

    serial = score_moca_task(
        "attention_serial",
        "93 | 86 | 80 | 79 | 72 | 72",
    )
    sequence = serial["task_analysis"]["sequence"]
    assert sequence["expected"] == [93, 86, 79, 72, 65]
    assert sequence["error_count"] > 0
    assert 72 in serial["task_analysis"]["repeated_elements"]["items"]


def test_summary_contains_aggregate_speech_metrics() -> None:
    tasks = [
        score_moca_task(
            "memory_1",
            "лицо бархат",
            acoustic_metrics=[
                {
                    "duration_seconds": 2.0,
                    "active_speech_seconds": 1.0,
                    "time_to_first_response_seconds": 0.5,
                    "pause_count": 1,
                    "total_pause_seconds": 0.3,
                }
            ],
        ),
        score_moca_task(
            "memory_2",
            "церковь фиалка",
            acoustic_metrics=[
                {
                    "duration_seconds": 3.0,
                    "active_speech_seconds": 2.0,
                    "time_to_first_response_seconds": 1.5,
                    "pause_count": 2,
                    "total_pause_seconds": 0.7,
                }
            ],
        ),
    ]

    summary = summarize_moca_tasks(tasks)["speech_summary"]

    assert summary["word_count"] == 4
    assert summary["duration_seconds"] == 5.0
    assert summary["words_per_minute"] == 48.0
    assert summary["words_per_active_minute"] == 80.0
    assert summary["pause_count"] == 3
    assert summary["total_pause_seconds"] == 1.0
    assert summary["average_time_to_first_response_seconds"] == 1.0


def test_moca_audio_saving_parameter_is_enabled_by_default() -> None:
    assert Settings().save_moca_audio is True


def test_moca_audio_saving_parameter_can_disable_copy() -> None:
    dataset_store = Mock()
    plugin = MocaTestPlugin(
        Mock(),
        settings=Settings(save_moca_audio=False),
        dataset_store=dataset_store,
    )
    plugin._session_id = "session-1"

    plugin._store_dataset_audio(
        "answer.wav",
        task=MocaTask("memory_1", "Память", ""),
        transcript="лицо",
    )

    dataset_store.store_answer_audio.assert_not_called()

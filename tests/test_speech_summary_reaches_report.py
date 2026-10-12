"""Речевые показатели доходят от расчёта до отчёта.

Расчёт существовал и работал, но его результат терялся: модуль теста выдавал
его в событии, аггрегатор в отчёт не переносил, интерфейс не показывал.
Измеренное, которое никуда не попадает, — то же самое, что неизмеренное.
"""
from __future__ import annotations

import inspect

from neuro_mirror.plugins.aggregator import plugin as aggregator_module
from neuro_mirror.screening.moca_scoring import score_moca_tasks

WITH_FILLERS = [
    {"task_id": "language_fluency",
     "transcript": "ну лодка как бы лампа лес лиса лето луна"},
    {"task_id": "language_sentence_2",
     "transcript": "кошка всегда пряталась под диваном когда собаки были в комнате"},
]


def test_the_test_result_carries_the_speech_summary():
    result = score_moca_tasks(WITH_FILLERS)
    assert "speech_summary" in result
    assert result["speech_summary"]["task_count"] == len(WITH_FILLERS)


def test_fillers_and_repetitions_are_counted():
    """Это и есть то, ради чего показатели считаются."""
    summary = score_moca_tasks(WITH_FILLERS)["speech_summary"]
    assert summary["fillers"]["count"] == 2
    assert set(summary["fillers"]["items"]) == {"ну", "как бы"}


def test_lexical_diversity_is_withheld_on_short_answers():
    """На коротком тексте доля уникальных слов почти всегда единица."""
    summary = score_moca_tasks(WITH_FILLERS)["speech_summary"]
    assert summary["lexical_diversity"] is None
    assert summary["word_count"] < summary["lexical_diversity_min_words"]


def test_lexical_diversity_is_measured_on_a_long_enough_answer():
    long_answer = [{
        "task_id": "language_fluency",
        "transcript": " ".join(
            "лодка лампа лес лиса лето луна лужа лимон лыжи лось "
            "лента лапа ларёк лавка лужайка лекарь лимонад лосось лыжник лунка".split()
        ),
    }]
    summary = score_moca_tasks(long_answer)["speech_summary"]
    assert summary["lexical_diversity"] is not None
    assert 0.0 < summary["lexical_diversity"] <= 1.0


def test_acoustic_values_stay_empty_without_recordings():
    """Пустое поле означает «измерить было нечем», а не ноль."""
    summary = score_moca_tasks(WITH_FILLERS)["speech_summary"]
    assert summary["duration_seconds"] is None
    assert summary["words_per_minute"] is None


def test_the_aggregator_carries_the_summary_into_the_report():
    """Без переноса показатели считались и терялись."""
    source = inspect.getsource(aggregator_module)
    assert '"moca_speech_summary"' in source


def test_the_specialist_report_shows_the_summary():
    """Речевые маркеры видит специалист, с пометкой методологии.

    Пользователю они не показываются: в его виде отчёта поля нет.
    """
    from pathlib import Path

    from neuro_mirror.screening.report_views import USER_DOMAINS, specialist_report

    report = specialist_report(
        [{"report_type": "moca", "domains": {"moca_speech_summary": {"words_per_minute": 90}}}],
        sessions=[],
    )
    markers = report["moca"][0]["speech_markers"]
    assert markers["values"]["words_per_minute"] == 90
    # Методология скрининга 2.0: речевые показатели — исследовательские.
    assert markers["note"] == "Исследовательский показатель, не для клинической интерпретации."
    assert "moca_speech_summary" not in USER_DOMAINS

    screen = (
        Path(aggregator_module.__file__).parents[2]
        / "web" / "static" / "js" / "screens" / "specialist-report.js"
    )
    text = screen.read_text(encoding="utf-8")
    assert "Речевые маркеры" in text
    assert "markers.note" in text

"""Пауза, продолжение с прерванной пробы, зерно и лимит времени во всех играх.

«Методика подбора и оценки тренировочного курса» v2: 4.5, п. 4–5 (пауза и
повтор прерванной пробы), 6.2 (статусы завершения), 6.5 (зерно случайности),
раздел 7 (лимит времени GM-01 и GM-10).
"""
from __future__ import annotations

import pytest

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.plugins.games.base import (
    END_ATTEMPTS,
    END_DONE,
    END_TIMEOUT,
    U06_SUCCESS,
    U06_TECHNICAL_INVALID,
    U06_TIMEOUT,
    U06_UNDETERMINED,
    U06_UNSUCCESSFUL,
    u06_status,
)
from neuro_mirror.plugins.games.registry import discover_game_registrations

REGISTRATIONS = {item.definition.code: item for item in discover_game_registrations()}
CODES = sorted(REGISTRATIONS)


def plugin_for(code):
    return REGISTRATIONS[code].plugin_class(EventBus())


def stable(value):
    """Ответ игры без того, что меняется от запуска к запуску: идентификаторов и времени."""
    if isinstance(value, dict):
        return {
            key: stable(item) for key, item in value.items()
            if key not in {"session_id", "id", "odd_id", "time_left_ms"} and not key.endswith("_ms")
        }
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


def test_every_game_is_covered():
    assert len(CODES) == 24


@pytest.mark.parametrize("code", CODES)
def test_the_same_seed_gives_the_same_task(code):
    """Задание курса с тем же зерном предъявляет те же стимулы (6.5)."""
    first = plugin_for(code).start_game({"randomization_seed": 4242, "difficulty_level": 1})
    second = plugin_for(code).start_game({"randomization_seed": 4242, "difficulty_level": 1})
    assert first["ok"] and second["ok"]
    assert stable(first) == stable(second)


@pytest.mark.parametrize("code", CODES)
def test_after_a_pause_the_interrupted_trial_is_presented_again(code):
    plugin = plugin_for(code)
    started = plugin.start_game({"randomization_seed": 7, "difficulty_level": 1})
    session_id = started["session_id"]
    paused = plugin.answer_game({"session_id": session_id, "action": "pause"})
    assert paused["ok"] and paused["trial"] == 1
    resumed = plugin.answer_game({"session_id": session_id, "action": "resume"})
    assert resumed["ok"], resumed
    assert resumed["resumed"] is True
    assert resumed["session_id"] == session_id
    assert resumed["interrupted_trial"] == 1
    assert resumed["finished"] is False
    # Пауза — служебное действие: ни контрольной точки, ни отчёта
    assert "checkpoint" not in resumed and "report" not in resumed


@pytest.mark.parametrize("code", CODES)
def test_an_unknown_session_is_started_over(code):
    reply = plugin_for(code).answer_game({"session_id": "нет-такой", "action": "resume"})
    assert reply["ok"] is False and reply["resumable"] is False


def test_a_screen_interrupted_mid_task_is_shown_again_unscored():
    """GM-07: прерванный экран показывается снова, ответы до него сохранены."""
    plugin = plugin_for("GM-07")
    first = plugin.start_game({"randomization_seed": 11, "difficulty_level": 1})
    second = plugin.answer_game({"session_id": first["session_id"], "selected_id": None})
    assert second["trial"] == 2
    plugin.answer_game({"session_id": first["session_id"], "action": "pause"})
    again = plugin.answer_game({"session_id": first["session_id"], "action": "resume"})
    assert again["trial"] == 2 and again["interrupted_trial"] == 2
    assert stable(again["stimuli"]) == stable(second["stimuli"])
    session = plugin._sessions[first["session_id"]]
    assert len(session.trials) == 1


def test_a_memory_room_is_studied_again_and_its_answers_are_dropped():
    """GM-03 — форма памяти: прерванная проба идёт с нового предъявления."""
    plugin = plugin_for("GM-03")
    started = plugin.start_game({"randomization_seed": 3, "difficulty_level": 1})
    sid = started["session_id"]
    recall = plugin.answer_game({"session_id": sid, "action": "begin_recall"})
    assert recall["phase"] == "recall"
    plugin.answer_game({"session_id": sid, "selected_cell": 0})
    assert len(plugin._sessions[sid].round_events) == 1
    plugin.answer_game({"session_id": sid, "action": "pause"})
    again = plugin.answer_game({"session_id": sid, "action": "resume"})
    assert again["phase"] == "study" and again["objects"]
    assert plugin._sessions[sid].round_events == []


def test_a_pair_board_starts_over_with_new_layout_and_no_moves():
    plugin = plugin_for("GM-01")
    started = plugin.start_game({"randomization_seed": 5, "difficulty_level": 1})
    sid = started["session_id"]
    plugin.answer_game({"session_id": sid, "selected_index": 0})
    plugin.answer_game({"session_id": sid, "selected_index": 1})
    assert plugin._sessions[sid].round_events
    plugin.answer_game({"session_id": sid, "action": "pause"})
    again = plugin.answer_game({"session_id": sid, "action": "resume"})
    assert again["board"] == 1 and again["matched"] == []
    assert sorted(again["cards"]) == sorted(started["cards"])
    assert plugin._sessions[sid].round_events == []


# ---- Лимит времени (GM-01, GM-10) ----


@pytest.mark.parametrize("code", ["GM-01", "GM-10"])
def test_the_task_reports_its_time_limit(code):
    started = plugin_for(code).start_game({"difficulty_level": 1})
    assert started["time_limit_ms"] > 0
    assert 0 < started["time_left_ms"] <= started["time_limit_ms"]
    assert started["time_visible"] is False


@pytest.mark.parametrize("code", ["GM-01", "GM-10"])
def test_the_core_does_not_end_the_task_before_its_time(code):
    plugin = plugin_for(code)
    started = plugin.start_game({"difficulty_level": 1})
    reply = plugin.answer_game({"session_id": started["session_id"], "action": "timeout"})
    assert reply["ok"] is False
    assert started["session_id"] in plugin._sessions


@pytest.mark.parametrize("code", ["GM-01", "GM-10"])
def test_out_of_time_ends_the_task_with_status_timeout(code):
    plugin = plugin_for(code)
    started = plugin.start_game({"difficulty_level": 1})
    plugin._sessions[started["session_id"]].clock.limit_ms = 0
    reply = plugin.answer_game({"session_id": started["session_id"], "action": "timeout"})
    assert reply["finished"] is True
    assert reply["end_reason"] == END_TIMEOUT
    assert reply["report"]["u06_status"] == U06_TIMEOUT
    assert reply["report"]["technical_validity"] == "valid"
    assert reply["report"]["completion_status"] == "incomplete"


def test_games_without_a_limit_refuse_a_timeout():
    plugin = plugin_for("GM-07")
    started = plugin.start_game({})
    reply = plugin.answer_game({"session_id": started["session_id"], "action": "timeout"})
    assert reply["ok"] is False
    assert started.get("time_limit_ms") is None


def test_gm02_first_error_means_attempts_are_exhausted():
    plugin = plugin_for("GM-02")
    started = plugin.start_game({"difficulty_level": 1})
    wrong = (started["sequence"][0] + 1) % 9
    reply = plugin.answer_game({
        "session_id": started["session_id"],
        "clicks": [{"cell": wrong, "timestamp_ms": 1}],
    })
    assert reply["finished"] is True
    assert reply["end_reason"] == END_ATTEMPTS
    assert reply["report"]["u06_status"] == U06_UNSUCCESSFUL


# ---- Статус U06 (6.2) ----


@pytest.mark.parametrize(
    ("metrics", "reason", "status"),
    [
        ({"u06_complete": True, "u06_technically_valid": True}, END_DONE, U06_SUCCESS),
        ({"u06_complete": False, "u06_technically_valid": True}, END_ATTEMPTS, U06_UNSUCCESSFUL),
        ({"u06_complete": False, "u06_technically_valid": True}, END_TIMEOUT, U06_TIMEOUT),
        ({"u06_complete": True, "u06_technically_valid": False}, END_DONE, U06_TECHNICAL_INVALID),
        ({}, END_DONE, U06_UNDETERMINED),
    ],
)
def test_u06_status_is_computed_from_the_metrics(metrics, reason, status):
    assert u06_status(metrics, reason) == status

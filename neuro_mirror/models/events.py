from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class Topics:
    SYSTEM_BOOTSTRAP = "system.bootstrap"
    AI_COMMAND = "ai.command"
    UI_ACTION = "ui.action"
    UI_DEVICE_SELECTED = "ui.device_selected"
    UI_DEVICE_WIZARD_OPEN = "ui.device_wizard.open"
    UI_UPDATE = "cmd.ui_update"
    PREPARE_SESSION = "cmd.prepare_session"
    START_CAPTURE = "cmd.start_capture"
    START_TEST = "cmd.start_test"
    DEVICE_SELECTION_RESOLVED = "device.selection_resolved"
    DEVICE_VALIDATION_FAILED = "device.validation_failed"
    SENSOR_VIDEO_FRAME = "sensor.video_frame"
    SENSOR_AUDIO_CHUNK = "sensor.audio_chunk"
    ANALYSIS_RESULT = "analysis.video_result"
    VOICE_TEST_RESULT = "test.voice_result"
    MOCA_START = "cmd.moca_start"
    MOCA_STOP = "cmd.moca_stop"
    MOCA_TEST_RESULT = "test.moca_result"
    HADS_START = "cmd.hads_start"
    HADS_STOP = "cmd.hads_stop"
    HADS_TEST_RESULT = "test.hads_result"
    SESSION_CHECKPOINT = "session.checkpoint"
    SESSION_ERROR = "session.error"
    GAME_SESSION_STARTED = "game.session.started"
    GAME_SESSION_CHECKPOINT = "game.session.checkpoint"
    GAME_SESSION_COMPLETED = "game.session.completed"
    REPORT_DATA = "report.data"
    USER_SELECTED = "user.selected"
    STORAGE_WRITE = "storage.write"
    STORAGE_READ = "storage.read"
    STORAGE_READ_RESULT = "storage.read_result"
    REQ_STORAGE_QUERY = "req.storage.query"
    RESP_STORAGE_QUERY = "resp.storage.query"

    # Request-reply topics: web layer sends a request, plugin replies
    REQ_SPEECH_TRANSCRIBE = "req.speech.transcribe"
    RESP_SPEECH_TRANSCRIBE = "resp.speech.transcribe"
    RPPG_RESULT = "rppg.result"


@dataclass(slots=True)
class Event:
    topic: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

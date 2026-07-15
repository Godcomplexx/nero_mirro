from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class Topics:
    SYSTEM_BOOTSTRAP = "system.bootstrap"
    VOICE_INTENT = "voice.intent"
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
    MOCA_TASK_RESULT = "test.moca_task_result"
    MOCA_TEST_RESULT = "test.moca_result"
    HADS_START = "cmd.hads_start"
    HADS_STOP = "cmd.hads_stop"
    HADS_TEST_RESULT = "test.hads_result"
    REPORT_DATA = "report.data"
    USER_SELECTED = "user.selected"
    STORAGE_WRITE = "storage.write"
    STORAGE_READ = "storage.read"
    STORAGE_READ_RESULT = "storage.read_result"
    REQ_STORAGE_QUERY = "req.storage.query"
    RESP_STORAGE_QUERY = "resp.storage.query"

    # Request-reply topics: web layer sends a request, plugin replies
    REQ_ASSISTANT_MESSAGE = "req.assistant.message"
    RESP_ASSISTANT_MESSAGE = "resp.assistant.message"
    REQ_SPEECH_TRANSCRIBE = "req.speech.transcribe"
    RESP_SPEECH_TRANSCRIBE = "resp.speech.transcribe"
    REQ_APPEARANCE_ANALYZE = "req.appearance.analyze"
    RESP_APPEARANCE_ANALYZE = "resp.appearance.analyze"
    REQ_CAMERA_VISION = "req.camera.vision"
    RESP_CAMERA_VISION = "resp.camera.vision"
    REQ_TTS_SPEAK = "req.tts.speak"
    RESP_TTS_SPEAK = "resp.tts.speak"
    RPPG_RESULT = "rppg.result"


@dataclass(slots=True)
class Event:
    topic: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

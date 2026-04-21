from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class Topics:
    SYSTEM_BOOTSTRAP = "system.bootstrap"
    VOICE_INTENT = "voice.intent"
    AI_COMMAND = "ai.command"
    UI_ACTION = "ui.action"
    UI_UPDATE = "cmd.ui_update"
    START_CAPTURE = "cmd.start_capture"
    START_TEST = "cmd.start_test"
    ANALYSIS_RESULT = "analysis.video_result"
    VOICE_TEST_RESULT = "test.voice_result"
    REPORT_DATA = "report.data"
    STORAGE_WRITE = "storage.write"
    STORAGE_READ = "storage.read"
    STORAGE_READ_RESULT = "storage.read_result"


@dataclass(slots=True)
class Event:
    topic: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

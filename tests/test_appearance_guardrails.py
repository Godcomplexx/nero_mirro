from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.user_profiles import UserProfileStore
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.video_analysis.plugin import VisionWorkerPlugin
from neuro_mirror.web.app import create_app


def _face_check(*, detected: bool) -> dict[str, object]:
    return {
        "frame_ok": True,
        "face_detected": detected,
        "face_count": 1 if detected else 0,
        "face_ratio": 0.15 if detected else 0.0,
        "face_close_enough": detected,
        "brightness": 130.0,
        "brightness_ok": True,
        "detector_available": True,
        "advice": [] if detected else ["Лицо не видно — расположитесь напротив камеры."],
    }


def _web_client(tmp_path, bus: SimpleNamespace) -> TestClient:
    users = UserProfileStore(tmp_path)
    user = users.create_user(
        "Test",
        consent=True,
        personal_data_consent=True,
        audio_data_consent=True,
        video_data_consent=True,
    )
    users.select_user(user["id"])
    app = create_app()
    app.state.context = SimpleNamespace(
        user_store=users,
        runtime=SimpleNamespace(bus=bus),
        settings=Settings(),
    )
    return TestClient(app)


def test_appearance_endpoint_does_not_start_worker_without_face(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "neuro_mirror.screening.session_check.analyze_frame_conditions",
        lambda _image: _face_check(detected=False),
    )
    bus = SimpleNamespace(publish=AsyncMock(), request=AsyncMock())
    client = _web_client(tmp_path, bus)

    response = client.post(
        "/api/appearance/analyze",
        files={"image": ("frame.jpg", b"jpeg", "image/jpeg")},
    )

    assert response.status_code == 422
    assert "Лицо не видно" in response.json()["detail"]
    bus.publish.assert_not_awaited()
    bus.request.assert_not_awaited()
    client.close()


def test_appearance_endpoint_replaces_empty_ai_reply(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "neuro_mirror.screening.session_check.analyze_frame_conditions",
        lambda _image: _face_check(detected=True),
    )
    bus = SimpleNamespace(
        publish=AsyncMock(),
        request=AsyncMock(return_value={"reply": "—", "report": None}),
    )
    client = _web_client(tmp_path, bus)

    response = client.post(
        "/api/appearance/analyze",
        files={"image": ("frame.jpg", b"jpeg", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["reply"].startswith("Оценка не получена")
    bus.request.assert_awaited_once()
    client.close()


def test_vision_worker_does_not_publish_report_without_face():
    async def run() -> None:
        bus = EventBus()
        responses = bus.subscribe(Topics.RESP_APPEARANCE_ANALYZE, Topics.REPORT_DATA)
        plugin = VisionWorkerPlugin(bus, settings=Settings(), appearance_composer=None)
        plugin._ensure_worker_started = AsyncMock()  # type: ignore[method-assign]
        plugin.worker.request = AsyncMock(
            return_value=SimpleNamespace(ok=True, result={"face_detected": False}, error_message="")
        )

        await plugin.handle_event(
            Event(
                topic=Topics.REQ_APPEARANCE_ANALYZE,
                source="test",
                payload={"_request_id": "request-1", "image_path": "frame.jpg"},
            )
        )

        response = await asyncio.wait_for(responses.queue.get(), timeout=1)
        assert response.topic == Topics.RESP_APPEARANCE_ANALYZE
        assert response.payload["error_code"] == "face_not_detected"
        assert responses.queue.empty()

    asyncio.run(run())

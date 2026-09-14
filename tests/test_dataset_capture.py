"""Dataset capture: consent gating, storage layout and path safety."""
from __future__ import annotations

import json
import wave

import pytest

from neuro_mirror.core.dataset_store import (
    MAX_VIDEO_CHUNK_BYTES,
    DatasetCaptureError,
    DatasetStore,
)
from neuro_mirror.core.user_profiles import CONSENT_TEXT, CONSENT_TEXTS, UserProfileStore


# ── Consent ────────────────────────────────────────────────────────────────────

def test_dataset_consent_is_not_inherited_by_old_profiles(tmp_path):
    """A profile created before the dataset existed never agreed to retention."""
    users_path = tmp_path / "users.json"
    users_path.write_text(
        json.dumps([{
            "id": "u0001",
            "name": "Старый профиль",
            "consent": {"given": True, "text": CONSENT_TEXT, "timestamp": "2026-01-01T00:00:00+00:00"},
        }]),
        encoding="utf-8",
    )
    store = UserProfileStore(runtime_dir=tmp_path)

    assert store.has_consent("u0001", "audio") is True
    assert store.has_consent("u0001", "video") is True
    assert store.has_consent("u0001", "dataset") is False


def test_dataset_consent_is_off_unless_requested(tmp_path):
    store = UserProfileStore(runtime_dir=tmp_path)
    user = store.create_user("Иван", consent=True)
    assert store.has_consent(user["id"], "dataset") is False


def test_dataset_consent_requires_audio_and_video(tmp_path):
    store = UserProfileStore(runtime_dir=tmp_path)
    with pytest.raises(ValueError):
        store.create_user(
            "Иван",
            consent=True,
            audio_data_consent=False,
            dataset_consent=True,
        )


def test_dataset_consent_can_be_granted_and_withdrawn(tmp_path):
    store = UserProfileStore(runtime_dir=tmp_path)
    user = store.create_user("Иван", consent=True)

    store.set_consent(user["id"], "dataset", True)
    assert store.has_consent(user["id"], "dataset") is True

    store.set_consent(user["id"], "dataset", False)
    assert store.has_consent(user["id"], "dataset") is False


def test_withdrawing_audio_consent_also_withdraws_dataset(tmp_path):
    """Retention cannot outlive permission to record in the first place."""
    store = UserProfileStore(runtime_dir=tmp_path)
    user = store.create_user("Иван", consent=True, dataset_consent=True)
    assert store.has_consent(user["id"], "dataset") is True

    store.set_consent(user["id"], "audio", False)
    assert store.has_consent(user["id"], "dataset") is False


def test_combined_consent_text_excludes_retention():
    assert CONSENT_TEXTS["dataset"] not in CONSENT_TEXT


# ── Storage ────────────────────────────────────────────────────────────────────

def _wav(path, seconds=0.05, sample_rate=16000):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * int(sample_rate * seconds))
    return str(path)


@pytest.fixture()
def store(tmp_path):
    return DatasetStore(root=tmp_path / "dataset")


def test_answer_audio_is_copied_and_labelled(store, tmp_path):
    store.open_session("abc123", user_id="u0001", scenario="moca")
    source = _wav(tmp_path / "answer.wav")

    stored = store.store_answer_audio(
        "abc123",
        source_path=source,
        task_id="attention_serial",
        labels={"transcript": "девяносто три", "scenario": "moca"},
    )

    assert stored
    # The source is untouched: the caller still owns and deletes it
    assert (tmp_path / "answer.wav").exists()
    sidecar = json.loads(
        (store.root / "abc123" / "audio" / "0001_attention_serial.json").read_text("utf-8")
    )
    assert sidecar["task_id"] == "attention_serial"
    assert sidecar["transcript"] == "девяносто три"
    assert sidecar["audio_file"] == "0001_attention_serial.wav"


def test_answers_are_numbered_in_order(store, tmp_path):
    store.open_session("abc123", user_id="u0001", scenario="moca")
    for index in range(3):
        store.store_answer_audio(
            "abc123",
            source_path=_wav(tmp_path / f"a{index}.wav"),
            task_id=f"task_{index}",
        )
    names = sorted(item.name for item in (store.root / "abc123" / "audio").glob("*.wav"))
    assert names == ["0001_task_0.wav", "0002_task_1.wav", "0003_task_2.wav"]


def test_nothing_is_stored_without_an_open_session(store, tmp_path):
    source = _wav(tmp_path / "answer.wav")
    assert store.store_answer_audio("abc123", source_path=source, task_id="memory_1") == ""
    assert not (store.root / "abc123").exists()


def test_missing_source_file_is_ignored(store):
    store.open_session("abc123", user_id="u0001", scenario="moca")
    assert store.store_answer_audio("abc123", source_path="nope.wav", task_id="x") == ""


def test_video_chunks_are_stored_in_sequence(store):
    store.open_session("abc123", user_id="u0001", scenario="hads")
    store.append_video_chunk("abc123", data=b"first", sequence=0)
    store.append_video_chunk("abc123", data=b"second", sequence=1)

    video_dir = store.root / "abc123" / "video"
    assert (video_dir / "000000.webm").read_bytes() == b"first"
    assert (video_dir / "000001.webm").read_bytes() == b"second"
    index = [json.loads(line) for line in (video_dir / "index.jsonl").read_text("utf-8").splitlines()]
    assert [item["sequence"] for item in index] == [0, 1]


def test_audio_sidecar_carries_duration_and_server_clock_bounds(store, tmp_path):
    store.open_session("abc123", user_id="u0001", scenario="moca")
    source = _wav(tmp_path / "answer.wav", seconds=0.5)

    store.store_answer_audio(
        "abc123",
        source_path=source,
        task_id="memory_1",
        labels={
            "started_at": "2026-09-11T10:00:00+00:00",
            "finished_at": "2026-09-11T10:00:00.500000+00:00",
        },
    )

    sidecar = json.loads(
        (store.root / "abc123" / "audio" / "0001_memory_1.json").read_text("utf-8")
    )
    assert sidecar["duration_seconds"] == pytest.approx(0.5, abs=0.01)
    assert sidecar["started_at"] == "2026-09-11T10:00:00+00:00"
    assert sidecar["finished_at"] == "2026-09-11T10:00:00.500000+00:00"


def test_video_start_pins_the_browser_clock_to_the_server(store):
    store.open_session("abc123", user_id="u0001", scenario="moca")

    capture = store.register_video_start(
        "abc123",
        client_started_at="2026-09-11T10:00:00+00:00",
        mime_type="video/webm;codecs=vp9,opus",
    )

    assert capture["video_started_at"]
    assert capture["client_started_at"] == "2026-09-11T10:00:00+00:00"
    assert capture["clock_offset_ms"] is not None
    manifest = json.loads((store.root / "abc123" / "manifest.json").read_text("utf-8"))
    assert manifest["video_capture"]["mime_type"] == "video/webm;codecs=vp9,opus"


def test_video_start_requires_an_open_session(store):
    with pytest.raises(DatasetCaptureError):
        store.register_video_start("abc123", client_started_at="2026-09-11T10:00:00+00:00")


def test_chunk_offsets_are_recorded_for_alignment(store):
    store.open_session("abc123", user_id="u0001", scenario="hads")
    store.register_video_start("abc123", client_started_at="2026-09-11T10:00:00+00:00")
    store.append_video_chunk("abc123", data=b"a", sequence=0, offset_ms=5000.4)
    store.append_video_chunk("abc123", data=b"b", sequence=1, offset_ms=10001.0)

    index = [
        json.loads(line)
        for line in (store.root / "abc123" / "video" / "index.jsonl").read_text("utf-8").splitlines()
    ]
    assert [item["offset_ms"] for item in index] == [5000.4, 10001.0]


def test_chunk_offset_is_optional(store):
    store.open_session("abc123", user_id="u0001", scenario="hads")
    record = store.append_video_chunk("abc123", data=b"a", sequence=0)
    assert record["offset_ms"] is None


def test_oversized_video_chunk_is_rejected(store):
    store.open_session("abc123", user_id="u0001", scenario="hads")
    with pytest.raises(DatasetCaptureError):
        store.append_video_chunk("abc123", data=b"x" * (MAX_VIDEO_CHUNK_BYTES + 1), sequence=0)


def test_video_chunk_without_open_session_is_rejected(store):
    with pytest.raises(DatasetCaptureError):
        store.append_video_chunk("abc123", data=b"x", sequence=0)


@pytest.mark.parametrize("session_id", ["../escape", "a/b", "", "..", "x" * 65])
def test_path_traversal_in_session_id_is_rejected(store, session_id):
    with pytest.raises(DatasetCaptureError):
        store.append_video_chunk(session_id, data=b"x", sequence=0)
    assert store.is_open(session_id) is False


def test_manifest_records_result_on_close(store, tmp_path):
    store.open_session("abc123", user_id="u0001", scenario="moca", versions={"app": "0.7.0"})
    store.store_answer_audio("abc123", source_path=_wav(tmp_path / "a.wav"), task_id="memory_1")
    store.append_video_chunk("abc123", data=b"chunk", sequence=0)
    assert store.is_open("abc123") is True

    store.close_session("abc123", status="completed", result={"moca_score": 12})

    manifest = json.loads((store.root / "abc123" / "manifest.json").read_text("utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["audio_count"] == 1
    assert manifest["video_chunk_count"] == 1
    assert manifest["result"]["moca_score"] == 12
    assert manifest["versions"] == {"app": "0.7.0"}
    assert store.is_open("abc123") is False


def test_timeline_is_append_only(store):
    store.open_session("abc123", user_id="u0001", scenario="hads")
    store.append_timeline("abc123", {"stage": "capture_started", "screen": "hads"})
    store.append_timeline("abc123", {"stage": "capture_stopped", "screen": "summary"})

    lines = (store.root / "abc123" / "timeline.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(line)["stage"] for line in lines] == ["capture_started", "capture_stopped"]


# ── HTTP layer ─────────────────────────────────────────────────────────────────

def _client(tmp_path, *, dataset_consent: bool, sessions=()):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi.testclient import TestClient

    from neuro_mirror.web.app import create_app

    users = UserProfileStore(runtime_dir=tmp_path)
    user = users.create_user("Иван", consent=True, dataset_consent=dataset_consent)
    users.select_user(user["id"])

    dataset_store = DatasetStore(root=tmp_path / "dataset")
    session_store = SimpleNamespace(list_for_user=lambda _user_id, **_: list(sessions))
    app = create_app()
    app.state.context = SimpleNamespace(
        user_store=users,
        runtime=SimpleNamespace(
            bus=SimpleNamespace(publish=AsyncMock()),
            dataset_store=dataset_store,
            session_store=session_store,
        ),
    )
    return TestClient(app), dataset_store, user


def test_video_chunk_requires_dataset_consent(tmp_path):
    client, _store, _user = _client(tmp_path, dataset_consent=False)
    response = client.post(
        "/api/dataset/video-chunk",
        data={"session_id": "abc123", "sequence": "0"},
        files={"chunk": ("0.webm", b"payload", "video/webm")},
    )
    assert response.status_code == 403
    client.close()


def test_video_chunk_rejected_when_capture_is_not_open(tmp_path):
    client, _store, _user = _client(tmp_path, dataset_consent=True)
    response = client.post(
        "/api/dataset/video-chunk",
        data={"session_id": "abc123", "sequence": "0"},
        files={"chunk": ("0.webm", b"payload", "video/webm")},
    )
    assert response.status_code == 409
    client.close()


def test_video_chunk_is_stored_for_an_open_session(tmp_path):
    client, store, user = _client(tmp_path, dataset_consent=True)
    store.open_session("abc123", user_id=user["id"], scenario="moca")

    response = client.post(
        "/api/dataset/video-chunk",
        data={"session_id": "abc123", "sequence": "0"},
        files={"chunk": ("0.webm", b"payload", "video/webm")},
    )

    assert response.status_code == 200
    assert (store.root / "abc123" / "video" / "000000.webm").read_bytes() == b"payload"
    client.close()


def test_video_start_endpoint_requires_dataset_consent(tmp_path):
    client, _store, _user = _client(tmp_path, dataset_consent=False)
    response = client.post(
        "/api/dataset/video-start",
        json={"session_id": "abc123", "client_started_at": "2026-09-11T10:00:00+00:00"},
    )
    assert response.status_code == 403
    client.close()


def test_video_start_endpoint_records_reference_point(tmp_path):
    client, store, user = _client(tmp_path, dataset_consent=True)
    store.open_session("abc123", user_id=user["id"], scenario="moca")

    response = client.post(
        "/api/dataset/video-start",
        json={"session_id": "abc123", "client_started_at": "2026-09-11T10:00:00+00:00"},
    )

    assert response.status_code == 200
    assert response.json()["video_started_at"]
    client.close()


def test_chunk_endpoint_passes_offset_through(tmp_path):
    client, store, user = _client(tmp_path, dataset_consent=True)
    store.open_session("abc123", user_id=user["id"], scenario="moca")

    response = client.post(
        "/api/dataset/video-chunk",
        data={"session_id": "abc123", "sequence": "0", "offset_ms": "4998.7"},
        files={"chunk": ("0.webm", b"payload", "video/webm")},
    )

    assert response.status_code == 200
    assert response.json()["offset_ms"] == 4998.7
    client.close()


def test_status_reports_capture_only_with_consent_and_open_session(tmp_path):
    sessions = [{"session_id": "abc123", "status": "in_progress", "scenario": "moca"}]
    client, store, user = _client(tmp_path, dataset_consent=True, sessions=sessions)

    assert client.get("/api/dataset/status").json()["capture"] is False

    store.open_session("abc123", user_id=user["id"], scenario="moca")
    body = client.get("/api/dataset/status").json()
    assert body["capture"] is True
    assert body["session_id"] == "abc123"
    client.close()


def test_start_action_reports_dataset_permission(tmp_path):
    client, _store, _user = _client(tmp_path, dataset_consent=True)
    assert client.post("/api/actions/start_moca").status_code == 200
    payload = client.app.state.context.runtime.bus.publish.await_args.args[0].payload
    assert payload["dataset_allowed"] is True
    assert payload["dataset_consent"]["given"] is True
    client.close()


def test_start_action_denies_dataset_without_consent(tmp_path):
    client, _store, _user = _client(tmp_path, dataset_consent=False)
    assert client.post("/api/actions/start_moca").status_code == 200
    payload = client.app.state.context.runtime.bus.publish.await_args.args[0].payload
    assert payload["dataset_allowed"] is False
    assert "dataset_consent" not in payload
    client.close()

"""Raw audio/video capture for building a research dataset.

Unlike :class:`~neuro_mirror.core.session_store.SessionStore`, which keeps
de-identified results, this store deliberately retains **identifying** material:
voice recordings and webcam video. It therefore writes nothing at all unless the
active profile granted the separate ``dataset`` consent, which is off by default
and is never inherited from the older combined consent.

Layout::

    runtime/dataset/<session_id>/
        manifest.json        session, scenario, versions, consent record
        timeline.jsonl       stage changes, one JSON object per line
        audio/0001_<task>.wav
        audio/0001_<task>.json   labels: task, transcript, score, timings
        video/000000.webm        chunks as produced by the browser
        video/index.jsonl        one record per stored chunk

Metadata is redacted the same way session records are; the media itself cannot
be de-identified and is the whole point of the dataset.
"""
from __future__ import annotations

import contextlib
import json
import logging
import re
import shutil
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neuro_mirror.core.data_redaction import redact_test_data

logger = logging.getLogger(__name__)

# Session ids are uuid4 hex, but the video endpoint accepts one from the
# browser — keep the pattern strict so it can never escape the dataset root.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TASK_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")

MAX_VIDEO_CHUNK_BYTES = 16 * 1024 * 1024
MAX_SESSION_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_VIDEO_CHUNKS = 100_000


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _wav_duration_seconds(path: Path) -> float | None:
    """Exact duration read from the file itself, not from a caller's estimate."""
    with contextlib.suppress(OSError, wave.Error, ZeroDivisionError):
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            if rate:
                return round(handle.getnframes() / rate, 3)
    return None


def _clock_offset_ms(server_iso: str, client_iso: str) -> float | None:
    """Server clock minus browser clock, so browser stamps can be translated."""
    with contextlib.suppress(ValueError, TypeError):
        server = datetime.fromisoformat(server_iso)
        client = datetime.fromisoformat(client_iso)
        return round((server - client).total_seconds() * 1000.0, 1)
    return None


class DatasetCaptureError(RuntimeError):
    """Raised when a caller asks for capture that must not happen."""


class DatasetStore:
    """Stores raw answers and session video for later model training."""

    def __init__(self, root: str | Path = "runtime/dataset") -> None:
        self.root = Path(root)
        self._video_bytes: dict[str, int] = {}

    # ---- Session lifecycle ----

    def open_session(
        self,
        session_id: str,
        *,
        user_id: str,
        scenario: str,
        versions: dict[str, Any] | None = None,
        consent: dict[str, Any] | None = None,
    ) -> Path:
        """Create the session folder and record why capture is allowed."""
        directory = self._session_dir(session_id)
        (directory / "audio").mkdir(parents=True, exist_ok=True)
        (directory / "video").mkdir(parents=True, exist_ok=True)
        manifest = {
            "session_id": session_id,
            "user_id": user_id,
            "scenario": scenario,
            "started_at": _utc_now(),
            "finished_at": None,
            "status": "in_progress",
            "versions": redact_test_data(versions or {}),
            "consent": redact_test_data(consent or {}),
            "audio_count": 0,
            "video_chunk_count": 0,
        }
        self._write_json(directory / "manifest.json", manifest)
        self._video_bytes[session_id] = 0
        logger.info("dataset: сессия %s открыта для записи (%s)", session_id, scenario)
        return directory

    def close_session(
        self,
        session_id: str,
        *,
        status: str = "completed",
        result: dict[str, Any] | None = None,
    ) -> None:
        directory = self._session_dir(session_id, create=False)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = self._read_json(manifest_path)
        manifest["status"] = status
        manifest["finished_at"] = _utc_now()
        manifest["audio_count"] = len(list((directory / "audio").glob("*.wav")))
        manifest["video_chunk_count"] = len(list(
            (directory / "video").glob("[0-9][0-9][0-9][0-9][0-9][0-9].webm")
        ))
        if result is not None:
            manifest["result"] = redact_test_data(result)
        self._write_json(manifest_path, manifest)
        self._video_bytes.pop(session_id, None)
        logger.info(
            "dataset: сессия %s закрыта (%s): %d аудио, %d видеофрагментов",
            session_id, status, manifest["audio_count"], manifest["video_chunk_count"],
        )

    def is_open(self, session_id: str) -> bool:
        if not session_id or not SESSION_ID_RE.match(session_id):
            return False
        manifest_path = self.root / session_id / "manifest.json"
        if not manifest_path.exists():
            return False
        return self._read_json(manifest_path).get("status") == "in_progress"

    def session_exists(self, session_id: str) -> bool:
        """Return whether a validated dataset session has already been created."""
        if not session_id or not SESSION_ID_RE.match(session_id):
            return False
        return (self.root / session_id / "manifest.json").is_file()

    def next_video_sequence(self, session_id: str) -> int:
        """Return the first unused browser video chunk number."""
        if not self.session_exists(session_id):
            return 0
        video_dir = self.root / session_id / "video"
        sequences = [
            int(item.stem)
            for item in video_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9].webm")
            if item.stem.isdigit()
        ]
        return max(sequences, default=-1) + 1

    # ---- Answers ----

    def store_answer_audio(
        self,
        session_id: str,
        *,
        source_path: str,
        task_id: str,
        labels: dict[str, Any] | None = None,
    ) -> str:
        """Copy a finished answer recording into the dataset and label it.

        The caller keeps ownership of ``source_path`` and still deletes it: the
        file is copied, never moved, so a failure here cannot break the test.
        Returns the stored path, or an empty string when nothing was written.
        """
        if not source_path:
            return ""
        source = Path(source_path)
        if not source.is_file():
            return ""
        directory = self._session_dir(session_id, create=False)
        audio_dir = directory / "audio"
        if not audio_dir.is_dir():
            return ""

        safe_task = TASK_ID_RE.sub("_", task_id).strip("_") or "answer"
        index = len(list(audio_dir.glob("*.wav"))) + 1
        stem = f"{index:04d}_{safe_task}"
        target = audio_dir / f"{stem}.wav"
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            logger.warning("dataset: не удалось сохранить аудио %s: %s", stem, exc)
            return ""

        record = {
            "session_id": session_id,
            "task_id": task_id,
            "audio_file": target.name,
            "duration_seconds": _wav_duration_seconds(target),
            "stored_at": _utc_now(),
            **redact_test_data(dict(labels or {})),
        }
        self._write_json(audio_dir / f"{stem}.json", record)
        return str(target)

    # ---- Video ----

    def register_video_start(
        self,
        session_id: str,
        *,
        client_started_at: str,
        mime_type: str = "",
    ) -> dict[str, Any]:
        """Pin the video timeline to the server clock.

        The browser owns the video clock and the server owns the audio clock,
        so one shared reference point is recorded here: the server time at which
        recording began, plus the browser's own idea of that same moment. Every
        chunk then carries its offset from this point, and every answer carries
        server start/end times — which makes the two tracks comparable.
        """
        directory = self._session_dir(session_id, create=False)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            raise DatasetCaptureError("Запись для этой сессии не открыта.")

        server_started_at = _utc_now()
        capture = {
            "video_started_at": server_started_at,
            "client_started_at": client_started_at,
            "clock_offset_ms": _clock_offset_ms(server_started_at, client_started_at),
            "mime_type": mime_type,
            "reference": (
                "Смещения фрагментов video/index.jsonl отсчитываются от "
                "video_started_at по часам сервера; те же часы у started_at "
                "в разметке аудиоответов."
            ),
        }
        manifest = self._read_json(manifest_path)
        manifest["video_capture"] = capture
        self._write_json(manifest_path, manifest)
        return capture

    def append_video_chunk(
        self,
        session_id: str,
        *,
        data: bytes,
        sequence: int,
        mime_type: str = "video/webm",
        offset_ms: float | None = None,
    ) -> dict[str, Any]:
        """Append one browser-produced media chunk to the session."""
        if not data:
            raise DatasetCaptureError("Пустой видеофрагмент.")
        if len(data) > MAX_VIDEO_CHUNK_BYTES:
            raise DatasetCaptureError("Видеофрагмент слишком большой.")
        if not 0 <= sequence < MAX_VIDEO_CHUNKS:
            raise DatasetCaptureError("Некорректный номер видеофрагмента.")

        directory = self._session_dir(session_id, create=False)
        video_dir = directory / "video"
        if not video_dir.is_dir():
            raise DatasetCaptureError("Запись для этой сессии не открыта.")

        written = self._video_bytes.get(session_id)
        if written is None:
            written = sum(
                item.stat().st_size
                for item in video_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9].webm")
            )
        if written + len(data) > MAX_SESSION_VIDEO_BYTES:
            raise DatasetCaptureError("Достигнут предел объёма видео для сессии.")

        suffix = ".webm" if "webm" in mime_type else ".bin"
        target = video_dir / f"{sequence:06d}{suffix}"
        target.write_bytes(data)
        self._video_bytes[session_id] = written + len(data)

        # MediaRecorder timeslices after the first are continuations of one
        # WebM stream. Keep them for recovery and also produce one playable
        # stream containing the chunks in browser sequence order.
        complete_path = video_dir / "session.webm"
        if sequence == 0:
            complete_path.write_bytes(data)
        elif complete_path.exists():
            with complete_path.open("ab") as complete:
                complete.write(data)
        else:
            temp_path = video_dir / "session.webm.tmp"
            with temp_path.open("wb") as complete:
                for item in sorted(video_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9].webm")):
                    complete.write(item.read_bytes())
            temp_path.replace(complete_path)

        record = {
            "sequence": sequence,
            "file": target.name,
            "bytes": len(data),
            "mime_type": mime_type,
            # Milliseconds from video_started_at to the end of this chunk.
            "offset_ms": round(offset_ms, 1) if offset_ms is not None else None,
            "received_at": _utc_now(),
            "complete_file": complete_path.name,
        }
        self._append_line(video_dir / "index.jsonl", record)

        # A final browser chunk may arrive after close_session(). Keep the
        # closed manifest accurate without reopening the session.
        manifest_path = directory / "manifest.json"
        manifest = self._read_json(manifest_path)
        manifest["video_chunk_count"] = len(list(
            video_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9].webm")
        ))
        manifest["video_file"] = str(Path("video") / complete_path.name)
        self._write_json(manifest_path, manifest)
        return record

    # ---- Timeline ----

    def append_timeline(self, session_id: str, entry: dict[str, Any]) -> None:
        """Record what was on screen, so media can be aligned with stages."""
        directory = self._session_dir(session_id, create=False)
        if not directory.is_dir():
            return
        record = {"at": _utc_now(), **redact_test_data(dict(entry))}
        self._append_line(directory / "timeline.jsonl", record)

    # ---- Internals ----

    def _session_dir(self, session_id: str, *, create: bool = True) -> Path:
        if not session_id or not SESSION_ID_RE.match(session_id):
            raise DatasetCaptureError("Некорректный идентификатор сессии.")
        directory = self.root / session_id
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_path.replace(path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _append_line(path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

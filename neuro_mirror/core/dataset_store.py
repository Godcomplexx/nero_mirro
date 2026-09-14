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
        video/session.webm       one playable file for the whole session
        video/index.jsonl        one record per chunk, with its offset

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

# MediaRecorder emits one WebM stream split into timeslices: only the first
# carries the header, the rest are continuation clusters. Appending them in
# order yields a single playable file, so that is what gets stored — separate
# chunk files would each be unplayable on their own.
VIDEO_FILE_NAME = "session.webm"
# Relative path stored in the manifest. Kept POSIX-style on every platform so
# the dataset can be read where it was not recorded.
VIDEO_FILE_RELATIVE = f"video/{VIDEO_FILE_NAME}"
# A chunk that arrives before its predecessor waits here instead of corrupting
# the stream; normally empty, because the browser uploads sequentially.
PENDING_DIR_NAME = "pending"


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
        self._video_next: dict[str, int] = {}

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
        video_dir = directory / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        # A resumed session reopens a folder that already holds media. Its
        # video counter must survive: restarting numbering at zero would splice
        # a second WebM header into the middle of the existing stream.
        previous = self._read_json(directory / "manifest.json")
        manifest = {
            "session_id": session_id,
            "user_id": user_id,
            "scenario": scenario,
            "started_at": previous.get("started_at") or _utc_now(),
            "finished_at": None,
            "status": "in_progress",
            "versions": redact_test_data(versions or {}),
            "consent": redact_test_data(consent or {}),
            "audio_count": len(list((directory / "audio").glob("*.wav"))),
            "video_chunk_count": previous.get("video_chunk_count") or 0,
        }
        for carried in ("video_capture", "video_file", "video_pending_chunks"):
            if carried in previous:
                manifest[carried] = previous[carried]
        self._write_json(directory / "manifest.json", manifest)
        self._video_bytes[session_id] = self._stored_video_bytes(video_dir)
        self._video_next.pop(session_id, None)
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
        manifest["video_chunk_count"] = self.next_video_sequence(session_id)
        pending = self._pending_sequences(directory / "video" / PENDING_DIR_NAME)
        manifest["video_pending_chunks"] = pending
        if result is not None:
            manifest["result"] = redact_test_data(result)
        self._write_json(manifest_path, manifest)
        self._video_bytes.pop(session_id, None)
        self._video_next.pop(session_id, None)
        logger.info(
            "dataset: сессия %s закрыта (%s): %d аудио, %d видеофрагментов",
            session_id, status, manifest["audio_count"], manifest["video_chunk_count"],
        )
        if pending:
            logger.warning(
                "dataset: сессия %s — видеофрагменты %s не встали в поток, "
                "видеозапись обрывается раньше конца сессии",
                session_id, pending,
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
        """Return the chunk number the stream expects next.

        Chunks are appended to one file, so the count of already appended
        chunks *is* the next expected sequence. A browser that reconnects to a
        resumed session continues its numbering from here.
        """
        if not self.session_exists(session_id):
            return 0
        cached = self._video_next.get(session_id)
        if cached is not None:
            return cached
        manifest = self._read_json(self.root / session_id / "manifest.json")
        try:
            restored = int(manifest.get("video_chunk_count") or 0)
        except (TypeError, ValueError):
            restored = 0
        restored = max(0, restored)
        self._video_next[session_id] = restored
        return restored

    @staticmethod
    def _pending_sequences(pending_dir: Path) -> list[int]:
        if not pending_dir.is_dir():
            return []
        return sorted(
            int(item.stem) for item in pending_dir.glob("*.part") if item.stem.isdigit()
        )

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
            written = self._stored_video_bytes(video_dir)
        if written + len(data) > MAX_SESSION_VIDEO_BYTES:
            raise DatasetCaptureError("Достигнут предел объёма видео для сессии.")

        expected = self.next_video_sequence(session_id)
        if sequence < expected:
            # A retried upload of a chunk already in the stream: appending it
            # again would duplicate video, so acknowledge without writing.
            return {
                "sequence": sequence,
                "file": VIDEO_FILE_RELATIVE,
                "bytes": 0,
                "mime_type": mime_type,
                "offset_ms": round(offset_ms, 1) if offset_ms is not None else None,
                "received_at": _utc_now(),
                "stored": "duplicate",
            }

        complete_path = video_dir / VIDEO_FILE_NAME
        pending_dir = video_dir / PENDING_DIR_NAME
        if sequence == expected:
            with complete_path.open("ab") as stream:
                stream.write(data)
            expected += 1
            expected = self._flush_pending(pending_dir, complete_path, expected)
            stored = "appended"
        else:
            # Out of order: hold it back rather than splice it into the wrong
            # place. The browser uploads sequentially, so this means an earlier
            # upload failed and is being retried.
            pending_dir.mkdir(parents=True, exist_ok=True)
            (pending_dir / f"{sequence:06d}.part").write_bytes(data)
            stored = "pending"

        self._video_next[session_id] = expected
        self._video_bytes[session_id] = written + len(data)

        record = {
            "sequence": sequence,
            "file": VIDEO_FILE_RELATIVE,
            "bytes": len(data),
            "mime_type": mime_type,
            # Milliseconds from video_started_at to the end of this chunk.
            "offset_ms": round(offset_ms, 1) if offset_ms is not None else None,
            "received_at": _utc_now(),
            "stored": stored,
        }
        self._append_line(video_dir / "index.jsonl", record)

        # A final browser chunk may arrive after close_session(). Keep the
        # closed manifest accurate without reopening the session.
        manifest_path = directory / "manifest.json"
        manifest = self._read_json(manifest_path)
        manifest["video_chunk_count"] = expected
        manifest["video_file"] = VIDEO_FILE_RELATIVE
        manifest["video_pending_chunks"] = self._pending_sequences(pending_dir)
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

    @staticmethod
    def _stored_video_bytes(video_dir: Path) -> int:
        total = 0
        complete_path = video_dir / VIDEO_FILE_NAME
        if complete_path.is_file():
            total += complete_path.stat().st_size
        pending_dir = video_dir / PENDING_DIR_NAME
        if pending_dir.is_dir():
            total += sum(item.stat().st_size for item in pending_dir.glob("*.part"))
        return total

    @classmethod
    def _flush_pending(cls, pending_dir: Path, complete_path: Path, expected: int) -> int:
        """Append held-back chunks that have become contiguous again."""
        if not pending_dir.is_dir():
            return expected
        while True:
            candidate = pending_dir / f"{expected:06d}.part"
            if not candidate.is_file():
                break
            with complete_path.open("ab") as stream:
                stream.write(candidate.read_bytes())
            candidate.unlink(missing_ok=True)
            expected += 1
        with contextlib.suppress(OSError):
            pending_dir.rmdir()  # only succeeds once nothing is held back
        return expected

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

"""Crash-tolerant local session records and resumable checkpoints."""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neuro_mirror.core.data_redaction import redact_test_data


ACTIVE_STATUSES = {"in_progress", "interrupted"}
FINAL_STATUSES = {"completed", "error"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SessionStore:
    """Persist complete session snapshots separately from user profiles.

    The file is replaced atomically so an interrupted write cannot leave a
    partially serialized JSON document in place.
    """

    def __init__(self, path: str | Path = "runtime/deidentified/sessions.json") -> None:
        self.path = Path(path)
        loaded = self._load()
        self._sessions: list[dict[str, Any]] = self._sanitize(loaded)
        self._persisted_sessions = deepcopy(self._sessions)
        recovered = self._recover_stale_sessions()
        if recovered or self._sessions != loaded:
            self._save()

    def start(
        self,
        *,
        user_id: str,
        scenario: str,
        versions: dict[str, Any],
        technical_params: dict[str, Any] | None = None,
        permissions: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        record = {
            "session_id": uuid.uuid4().hex,
            "user_id": user_id,
            "scenario": scenario,
            "status": "in_progress",
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "versions": deepcopy(versions),
            "technical_params": self._sanitize(technical_params or {}),
            "permissions": deepcopy(permissions or {}),
            "checkpoint": {},
            "result": None,
            "interruption_reason": "",
            "storage_path": str(self.path),
            "events": [
                {
                    "timestamp": now,
                    "type": "session_started",
                    "details": {"scenario": scenario},
                }
            ],
        }
        self._sessions.append(record)
        self._save()
        return deepcopy(self._find(record["session_id"]))

    def get(self, session_id: str) -> dict[str, Any] | None:
        record = self._find(session_id)
        return deepcopy(record) if record is not None else None

    def list_for_user(
        self,
        user_id: str,
        *,
        resumable_only: bool = False,
    ) -> list[dict[str, Any]]:
        items = [
            deepcopy(item)
            for item in self._sessions
            if item.get("user_id") == user_id
            and (not resumable_only or item.get("status") in ACTIVE_STATUSES)
        ]
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return items

    def add_event(
        self,
        session_id: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        record = self._find(session_id)
        if record is None:
            return None
        now = _utc_now()
        record.setdefault("events", []).append(
            {
                "timestamp": now,
                "type": event_type,
                "details": self._sanitize(details or {}),
            }
        )
        record["updated_at"] = now
        self._save()
        return deepcopy(self._find(record["session_id"]))

    def checkpoint(
        self,
        session_id: str,
        checkpoint: dict[str, Any],
    ) -> dict[str, Any] | None:
        record = self._find(session_id)
        if record is None:
            return None
        now = _utc_now()
        record["checkpoint"] = self._sanitize(checkpoint)
        record["updated_at"] = now
        record.setdefault("events", []).append(
            {
                "timestamp": now,
                "type": "checkpoint_saved",
                "details": {
                    "source": checkpoint.get("source", ""),
                    "next_index": checkpoint.get("next_index"),
                },
            }
        )
        self._save()
        return deepcopy(self._find(record["session_id"]))

    def interrupt(self, session_id: str, reason: str) -> dict[str, Any] | None:
        return self._finish(session_id, status="interrupted", reason=reason)

    def fail(self, session_id: str, reason: str) -> dict[str, Any] | None:
        return self._finish(session_id, status="error", reason=reason)

    def complete(
        self,
        session_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._finish(session_id, status="completed", result=result)

    def resume(
        self, session_id: str, *, user_id: str,
        permissions: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        record = self._find(session_id)
        if record is None:
            raise KeyError(session_id)
        if record.get("user_id") != user_id:
            raise PermissionError(session_id)
        if record.get("status") != "interrupted":
            raise ValueError("Возобновить можно только прерванную сессию.")
        now = _utc_now()
        record["status"] = "in_progress"
        record["finished_at"] = None
        record["interruption_reason"] = ""
        record["updated_at"] = now
        if permissions is not None:
            record["permissions"] = deepcopy(permissions)
        record.setdefault("events", []).append(
            {"timestamp": now, "type": "session_resumed", "details": {}}
        )
        self._save()
        return deepcopy(self._find(record["session_id"]))

    def _finish(
        self,
        session_id: str,
        *,
        status: str,
        reason: str = "",
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        record = self._find(session_id)
        if record is None:
            return None
        now = _utc_now()
        record["status"] = status
        record["updated_at"] = now
        record["finished_at"] = now if status in FINAL_STATUSES else None
        reason = self._sanitize(reason)
        record["interruption_reason"] = reason
        if result is not None:
            record["result"] = self._sanitize(result)
        record.setdefault("events", []).append(
            {
                "timestamp": now,
                "type": f"session_{status}",
                "details": {"reason": reason} if reason else {},
            }
        )
        self._save()
        return deepcopy(self._find(record["session_id"]))

    def _find(self, session_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in self._sessions if item.get("session_id") == session_id),
            None,
        )

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        parsed = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
            raise ValueError(f"Invalid sessions file: {self.path}")
        return parsed

    def _recover_stale_sessions(self) -> bool:
        """Mark sessions left in progress by a previous process as resumable."""
        changed = False
        now = _utc_now()
        for record in self._sessions:
            if record.get("status") != "in_progress":
                continue
            record["status"] = "interrupted"
            record["updated_at"] = now
            record["finished_at"] = None
            record["interruption_reason"] = (
                "Приложение было завершено до окончания сессии."
            )
            record.setdefault("events", []).append(
                {
                    "timestamp": now,
                    "type": "session_interrupted",
                    "details": {"reason": record["interruption_reason"]},
                }
            )
            changed = True
        return changed

    def _save(self) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._sessions = self._sanitize(self._sessions)
            temp_path.write_text(
                json.dumps(self._sessions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except BaseException:
            self._sessions = deepcopy(self._persisted_sessions)
            raise
        else:
            self._persisted_sessions = deepcopy(self._sessions)
        finally:
            temp_path.unlink(missing_ok=True)

    _sanitize = staticmethod(redact_test_data)

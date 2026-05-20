from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkerResponse:
    ok: bool
    result: dict[str, Any]
    error_code: str = ""
    error_message: str = ""


class WorkerClient:
    def __init__(
        self,
        *,
        name: str,
        python_executable: str,
        script_path: str,
        request_timeout_seconds: float,
        max_restart_attempts: int = 3,
    ) -> None:
        self.name = name
        self.python_executable = python_executable or sys.executable
        self.script_path = str(Path(script_path).resolve())
        self.request_timeout_seconds = request_timeout_seconds
        self.max_restart_attempts = max_restart_attempts
        self._process: subprocess.Popen[bytes] | None = None
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=20)
        self._stderr_thread: threading.Thread | None = None
        self._restart_count: int = 0
        self._last_restart_at: float = 0.0

    @property
    def last_stderr(self) -> str:
        return " | ".join(self._stderr_lines)

    async def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        await asyncio.to_thread(self._start_sync)

    async def stop(self) -> None:
        await asyncio.to_thread(self._stop_sync)

    async def request(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> WorkerResponse:
        effective_timeout = timeout if timeout is not None else self.request_timeout_seconds
        async with self._async_lock:
            return await asyncio.wait_for(
                asyncio.to_thread(self._request_sync, action, payload or {}),
                timeout=effective_timeout,
            )

    def _start_sync(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        self._process = subprocess.Popen(
            [self.python_executable, self.script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(self.script_path).parent.parent.parent),
        )
        self._stderr_thread = threading.Thread(target=self._consume_stderr_sync, name=f"{self.name}-stderr", daemon=True)
        self._stderr_thread.start()

    def _stop_sync(self) -> None:
        if self._process is None:
            return

        process = self._process

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

        for stream_name in ("stdin", "stdout", "stderr"):
            stream = getattr(process, stream_name, None)
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass

        self._process = None
        self._stderr_thread = None

    def _ensure_running_sync(self) -> None:
        """Restart worker if it has crashed, with exponential backoff."""
        if self._process is not None and self._process.poll() is None:
            return
        now = time.monotonic()
        backoff = min(2.0 ** self._restart_count, 30.0)
        if now - self._last_restart_at < backoff and self._restart_count > 0:
            raise RuntimeError(
                f"worker {self.name} crashed; next restart in "
                f"{backoff - (now - self._last_restart_at):.1f}s"
            )
        _log.warning("worker %s is not running — restarting (attempt %d)", self.name, self._restart_count + 1)
        self._stop_sync()
        self._start_sync()
        self._restart_count += 1
        self._last_restart_at = time.monotonic()

    def _request_sync(self, action: str, payload: dict[str, Any]) -> WorkerResponse:
        self._ensure_running_sync()

        message = {
            "id": uuid.uuid4().hex,
            "action": action,
            "payload": payload,
        }
        raw_request = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")

        with self._sync_lock:
            assert self._process.stdin is not None
            assert self._process.stdout is not None
            self._process.stdin.write(raw_request)
            self._process.stdin.flush()
            raw_line = self._process.stdout.readline()

        if not raw_line:
            raise RuntimeError(
                f"worker {self.name} closed stdout unexpectedly. stderr={self.last_stderr}"
            )

        parsed = json.loads(raw_line.decode("utf-8"))
        if parsed.get("id") != message["id"]:
            raise RuntimeError(f"worker {self.name} returned mismatched response id")

        if parsed.get("ok"):
            self._restart_count = 0  # successful response — reset backoff
            return WorkerResponse(ok=True, result=parsed.get("result") or {})

        error_payload = parsed.get("error") or {}
        return WorkerResponse(
            ok=False,
            result={},
            error_code=str(error_payload.get("code") or "worker_error"),
            error_message=str(error_payload.get("message") or "unknown worker error"),
        )

    def _consume_stderr_sync(self) -> None:
        if self._process is None or self._process.stderr is None:
            return

        import logging
        log = logging.getLogger(f"worker.{self.name}.stderr")
        for raw_line in self._process.stderr:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                self._stderr_lines.append(line)
                log.warning("%s", line)

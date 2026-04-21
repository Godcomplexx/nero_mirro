from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import Iterator


_GPU_LOCK = threading.Lock()


@contextmanager
def exclusive_gpu_task_sync(_task_name: str = "") -> Iterator[None]:
    _GPU_LOCK.acquire()
    try:
        yield
    finally:
        _GPU_LOCK.release()


@asynccontextmanager
async def exclusive_gpu_task(_task_name: str = ""):
    await asyncio.to_thread(_GPU_LOCK.acquire)
    try:
        yield
    finally:
        _GPU_LOCK.release()

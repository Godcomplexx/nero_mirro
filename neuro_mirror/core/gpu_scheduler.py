from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager


_GPU_LOCK = threading.Lock()


@asynccontextmanager
async def exclusive_gpu_task(_task_name: str = ""):
    await asyncio.to_thread(_GPU_LOCK.acquire)
    try:
        yield
    finally:
        _GPU_LOCK.release()

from __future__ import annotations

import asyncio

from neuro_mirror.app.runtime import create_runtime
from neuro_mirror.core.settings import Settings
from neuro_mirror.plugins.ui.plugin import ConsoleUIPlugin


async def run() -> int:
    settings = Settings.from_env()
    runtime = create_runtime(
        settings,
        stop_event=asyncio.Event(),
        include_ai_plugin=True,
    )
    runtime.plugin_manager.register(ConsoleUIPlugin(runtime.bus))

    await runtime.start()
    try:
        await runtime.bootstrap()
        await runtime.stop_event.wait()
    finally:
        await runtime.stop()

    return 0

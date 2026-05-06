from __future__ import annotations

from neuro_mirror.interfaces.plugin import Plugin


class PluginManager:
    def __init__(self) -> None:
        self._plugins: list[Plugin] = []

    def register(self, plugin: Plugin) -> None:
        self._plugins.append(plugin)

    async def start_all(self) -> None:
        for plugin in self._plugins:
            await plugin.start()

    async def stop_all(self) -> None:
        for plugin in reversed(self._plugins):
            await plugin.stop()



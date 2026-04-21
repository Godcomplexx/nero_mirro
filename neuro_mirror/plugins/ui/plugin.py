"""Console-only UI plugin for debug/headless mode."""

from __future__ import annotations

from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics


SCREEN_LABELS = {
    "idle": "Ожидание",
    "assistant": "Ассистент",
    "screening": "Скрининг",
    "summary": "Итог",
}


class ConsoleUIPlugin(Plugin):
    """Prints UI events to stdout. Used when running without the web server."""

    plugin_name = "console_ui"

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.UI_UPDATE,)

    async def handle_event(self, event: Event) -> None:
        payload = event.payload
        if payload.get("message") is None and payload.get("report") is None:
            return

        screen = SCREEN_LABELS.get(str(payload.get("screen", "")), str(payload.get("screen", "")))
        print(
            "[UI]",
            f"экран={screen}",
            f"сообщение={payload.get('message')}",
            f"источник={payload.get('assistant_source') or '-'}",
        )

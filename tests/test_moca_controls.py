"""Кнопки «Повторить инструкцию» и «Приступить» в когнитивном тесте.

Техническое задание требует обе кнопки и ограничение времени на задание.
Прежде модуль озвучивал инструкцию, сам записывал ответ и сам переходил
дальше: переслушать инструкцию или начать задание по готовности было нельзя.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.moca_test import plugin as moca_plugin
from neuro_mirror.plugins.moca_test.plugin import (
    MOCA_TASKS,
    START_GRACE_SECONDS,
    TASK_TIME_LIMIT_SECONDS,
    MocaTestPlugin,
    start_grace_seconds,
)


def a_plugin(bus, grace: float | None = None) -> MocaTestPlugin:
    settings = Settings()
    if grace is not None:
        object.__setattr__(settings, "moca_start_grace_seconds", grace)
    return MocaTestPlugin(bus, settings=settings)


async def press(plugin: MocaTestPlugin, action: str) -> None:
    await plugin.handle_event(
        Event(topic=Topics.UI_ACTION, source="test", payload={"action": action})
    )


# ── Ограничение времени ───────────────────────────────────────────────────────

def test_the_time_limit_follows_the_specification():
    """Ориентир технического задания — до двух минут на задание."""
    assert TASK_TIME_LIMIT_SECONDS == 120.0


def test_waiting_for_the_button_is_shorter_than_the_task_limit():
    """Ожидание нажатия — часть времени задания, а не добавка к нему."""
    assert 0 < START_GRACE_SECONDS < TASK_TIME_LIMIT_SECONDS


def test_the_waiting_time_can_be_turned_off():
    settings = Settings()
    object.__setattr__(settings, "moca_start_grace_seconds", 0.0)
    assert start_grace_seconds(settings) == 0.0


def test_a_negative_waiting_time_is_treated_as_none():
    settings = Settings()
    object.__setattr__(settings, "moca_start_grace_seconds", -5.0)
    assert start_grace_seconds(settings) == 0.0


# ── «Приступить к выполнению» ─────────────────────────────────────────────────

def test_the_task_starts_as_soon_as_the_button_is_pressed():
    """Ждать истечения паузы, когда человек готов, незачем."""
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus, grace=30.0)
        plugin._running = True
        updates = bus.subscribe(Topics.UI_UPDATE)

        waiting = asyncio.create_task(
            plugin._await_task_start(MOCA_TASKS[0], 0, len(MOCA_TASKS))
        )
        announcement = await asyncio.wait_for(updates.queue.get(), timeout=1)
        assert announcement.payload["moca_awaiting_start"] is True
        assert announcement.payload["moca_task_limit_seconds"] == TASK_TIME_LIMIT_SECONDS

        await press(plugin, "moca_begin_task")
        await asyncio.wait_for(waiting, timeout=1)

    asyncio.run(run())


def test_the_task_starts_by_itself_when_nobody_presses():
    """Иначе тест встанет на человеке, который кнопку не заметил."""
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus, grace=0.05)
        plugin._running = True
        await asyncio.wait_for(
            plugin._await_task_start(MOCA_TASKS[0], 0, len(MOCA_TASKS)), timeout=2
        )

    asyncio.run(run())


def test_the_interface_is_told_the_waiting_is_over():
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus, grace=0.05)
        plugin._running = True
        updates = bus.subscribe(Topics.UI_UPDATE)
        await plugin._await_task_start(MOCA_TASKS[0], 0, len(MOCA_TASKS))
        seen = []
        while not updates.queue.empty():
            seen.append(updates.queue.get_nowait().payload.get("moca_awaiting_start"))
        assert seen[0] is True and seen[-1] is False

    asyncio.run(run())


# ── «Повторить инструкцию» ────────────────────────────────────────────────────

def test_the_instruction_can_be_repeated_while_the_task_has_not_started():
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus)
        plugin._running = True
        plugin._current_prompt = "Назовите пять слов."
        plugin._speak = AsyncMock(return_value=True)

        await press(plugin, "moca_repeat_prompt")
        await asyncio.sleep(0)  # повтор идёт отдельной задачей
        plugin._speak.assert_awaited_once_with("Назовите пять слов.")

    asyncio.run(run())


def test_repeating_does_nothing_outside_a_running_test():
    """Нажатие на остановленном тесте не должно ничего озвучивать."""
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus)
        plugin._running = False
        plugin._current_prompt = "Назовите пять слов."
        plugin._speak = AsyncMock(return_value=True)

        await press(plugin, "moca_repeat_prompt")
        await asyncio.sleep(0)
        plugin._speak.assert_not_awaited()

    asyncio.run(run())


def test_repeating_does_not_block_other_commands():
    """Обработчик событий не должен ждать, пока договорит озвучка."""
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus)
        plugin._running = True
        plugin._current_prompt = "Длинная инструкция."

        async def slow(_text):
            await asyncio.sleep(5)
            return True

        plugin._speak = slow
        await asyncio.wait_for(press(plugin, "moca_repeat_prompt"), timeout=1)

    asyncio.run(run())


def test_an_unknown_command_is_ignored():
    async def run():
        bus = EventBus()
        plugin = a_plugin(bus)
        plugin._running = True
        plugin._speak = AsyncMock(return_value=True)
        await press(plugin, "moca_нет_такой_команды")
        plugin._speak.assert_not_awaited()

    asyncio.run(run())

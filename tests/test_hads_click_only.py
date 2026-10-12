"""HADS проходится кликами от начала до конца, без голоса.

ТЗ, модуль HADS: «Ввод ответов выбором варианта (без аудио-ввода
пациента)». Вопросы читаются вслух — голос дублирует текст, — но ответ
принимается только нажатием на вариант.
"""
from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.hads_test import plugin as hads_plugin
from neuro_mirror.screening.hads_scoring import HADS_QUESTIONS


def test_every_question_is_answered_by_click(monkeypatch):
    real_sleep = asyncio.sleep

    async def no_pause(_seconds, *args, **kwargs):
        await real_sleep(0)

    # Пауза после принятого ответа нужна человеку, а не тесту
    monkeypatch.setattr(hads_plugin.asyncio, "sleep", no_pause)

    async def run():
        bus = EventBus()
        transcriptions = bus.subscribe(Topics.REQ_SPEECH_TRANSCRIBE)
        updates = bus.subscribe(Topics.UI_UPDATE)
        results = bus.subscribe(Topics.HADS_TEST_RESULT)
        plugin = hads_plugin.HadsTestPlugin(bus, settings=Settings())
        await plugin.start()
        try:
            await bus.publish(Event(topic=Topics.HADS_START, source="test", payload={"session_id": "s1"}))
            answered = set()
            while len(answered) < len(HADS_QUESTIONS):
                update = (await asyncio.wait_for(updates.queue.get(), timeout=5)).payload
                assert "Отвечайте голосом" not in str(update.get("message") or "")
                if update.get("hads_tts_id"):
                    await bus.publish(Event(topic=Topics.UI_ACTION, source="test", payload={
                        "action": "hads_tts_finished", "hads_tts_id": update["hads_tts_id"]}))
                if update.get("message") == "Выберите вариант ответа на экране.":
                    index = update["hads_question_index"]
                    if index not in answered:
                        answered.add(index)
                        await bus.publish(Event(topic=Topics.UI_ACTION, source="test", payload={
                            "action": "hads_answer", "question_index": index, "option_index": 0}))
            result = (await asyncio.wait_for(results.queue.get(), timeout=5)).payload
            assert result["answered_count"] == len(HADS_QUESTIONS)
            assert result["stopped_early"] is False
            assert transcriptions.queue.empty(), "HADS не должен ничего распознавать"
        finally:
            await plugin.stop()
            for subscription in (transcriptions, updates, results):
                subscription.close()

    asyncio.run(run())

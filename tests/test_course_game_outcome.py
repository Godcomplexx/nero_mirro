"""Исход настоящей игры доходит до плана курса и меняет уровень формы.

По отдельности правило перехода, хранение курса и игры уже проверены; здесь
важен стык: игра закончилась — координатор записал исход в задание курса —
следующее занятие строится по нему.
"""
from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.catalog import get_game_definition
from neuro_mirror.plugins.games.coordinator import GameSessionCoordinator
from neuro_mirror.plugins.games.course_store import ITEM_DONE, TrainingCourseStore
from neuro_mirror.plugins.games.gm17_mental_rotation.plugin import Gm17MentalRotationPlugin
from neuro_mirror.plugins.games.history import GameHistoryStore
from neuro_mirror.screening.difficulty_policy import Success
from neuro_mirror.screening.training_course import form_states

ROTATION = get_game_definition("GM-17")


def course_with_rotation(store: TrainingCourseStore, number: int) -> dict:
    course = store.latest_course("u1") or store.create_course(
        user_id="u1", entry_session_id="moca-1", profile=[]
    )
    store.add_session(course, {
        "number": number,
        "stage": "mastering",
        "plan": {"Абстракция": 1},
        "skipped": [],
        "level_changes": [],
        "games": [{
            "position": 1,
            "domain": "Абстракция",
            "domain_code": "abstraction",
            "game_code": "GM-17",
            "title": ROTATION.title,
            "stimulus_set": ROTATION.stimulus_sets[1],
            "stimulus_set_number": 2,
            "randomization_seed": 1,
            "difficulty_level": 1,
            "adaptation": "adaptive",
            "flags": [],
            "reasons": [],
        }],
    })
    return course


async def play_rotation(bus: EventBus, plugin: Gm17MentalRotationPlugin, store: TrainingCourseStore, number: int) -> None:
    """Начать задание курса и ответить верно на все пробы."""
    item = store.begin_item(user_id="u1", session_number=number, position=1, game_code="GM-17")
    started = await bus.request(Event(
        topic=ROTATION.start_request_topic,
        source="test",
        payload={
            "user_id": "u1",
            "difficulty_level": item["difficulty_level"],
            "stimulus_set": item["stimulus_set"],
        },
    ))
    session_id = started["session_id"]
    store.attach_game_session(user_id="u1", session_number=number, position=1, game_session_id=session_id)
    reply = started
    while not reply.get("finished"):
        correct_id = plugin._sessions[session_id].correct_choice_id
        reply = await bus.request(Event(
            topic=ROTATION.answer_request_topic,
            source="test",
            payload={"session_id": session_id, "selected_id": correct_id, "timestamp_ms": 100.0},
        ))
    # Исход идёт к координатору отдельным событием после ответа игры.
    for _ in range(5):
        await asyncio.sleep(0)


def test_a_finished_game_reaches_the_course_and_raises_the_level(tmp_path) -> None:
    async def scenario() -> None:
        bus = EventBus()
        store = TrainingCourseStore(tmp_path / "courses.json")
        plugin = Gm17MentalRotationPlugin(bus)
        coordinator = GameSessionCoordinator(
            bus,
            session_store=SessionStore(tmp_path / "sessions.json"),
            history_store=GameHistoryStore(tmp_path / "history.json"),
            course_store=store,
        )
        stored = bus.subscribe(Topics.STORAGE_WRITE)
        await plugin.start()
        await coordinator.start()
        try:
            for number in (3, 4, 5):
                course = course_with_rotation(store, number)
                await play_rotation(bus, plugin, store, number)
                await asyncio.wait_for(stored.queue.get(), timeout=2)

                session = course["sessions"][-1]
                item = session["games"][0]
                assert item["status"] == ITEM_DONE
                assert item["counted"] is True
                assert Success(**item["success"]).at_least(85)
                assert session["status"] == "completed", "единственное задание выполнено"

            states, _ = form_states(store.passes(course), 6)
            assert states["GM-17"].level == 2
        finally:
            await coordinator.stop()
            await plugin.stop()
            stored.close()

    asyncio.run(scenario())

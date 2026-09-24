from __future__ import annotations

import asyncio
import collections

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.gm05_word_list.plugin import Gm05WordListPlugin
from neuro_mirror.plugins.games.gm08_stop_signal.plugin import Gm08StopSignalPlugin
from neuro_mirror.plugins.games.gm12_word_picture.plugin import Gm12WordPicturePlugin
from neuro_mirror.plugins.games.gm12_word_picture.stimuli import ITEMS as GM12_ITEMS
from neuro_mirror.plugins.games.gm19_maze.plugin import DIRS, Gm19MazePlugin
from neuro_mirror.plugins.games.gm23_matrix_reasoning.plugin import Gm23MatrixReasoningPlugin


async def _run_plugin(plugin, start_topic, answer_topic, answer_builder, expected: int) -> dict:
    await plugin.start()
    try:
        reply = await plugin.bus.request(Event(topic=start_topic, source="test"))
        count = 0
        while not reply.get("finished"):
            reply = await plugin.bus.request(Event(topic=answer_topic, source="test", payload=answer_builder(plugin, reply)))
            count += 1
        assert count == expected
        assert reply["metrics"]["u06_complete"] is True
        assert reply["report"]["game_code"].startswith("GM-")
        assert reply["report"]["completion_status"] == "completed"
        assert reply["report"]["technical_validity"] == "valid"
        assert len(reply["report"]["trials"]) == expected
        return reply
    finally:
        await plugin.stop()


def test_new_game_plugins_complete() -> None:
    async def scenario() -> None:
        bus = EventBus()
        await _run_plugin(
            Gm05WordListPlugin(bus), Topics.REQ_GM05_START, Topics.REQ_GM05_ANSWER,
            lambda plugin, reply: {"session_id": reply["session_id"], "selected": reply["study_words"], "timestamp_ms": 1}, 3,
        )

        bus = EventBus()
        await _run_plugin(
            Gm08StopSignalPlugin(bus), Topics.REQ_GM08_START, Topics.REQ_GM08_ANSWER,
            lambda plugin, reply: {"session_id": reply["session_id"], "responded": not reply["mirrored"],
                                   "reaction_ms": 300 if not reply["mirrored"] else None, "timestamp_ms": 1}, 40,
        )

        bus = EventBus()
        gm12_result = await _run_plugin(
            Gm12WordPicturePlugin(bus), Topics.REQ_GM12_START, Topics.REQ_GM12_ANSWER,
            lambda plugin, reply: {"session_id": reply["session_id"],
                                   "selected_word": plugin._sessions[reply["session_id"]].order[plugin._sessions[reply["session_id"]].index][1],
                                   "timestamp_ms": 1}, len(GM12_ITEMS),
        )
        assert gm12_result["checkpoint"]["next_index"] == len(GM12_ITEMS)
        assert len(gm12_result["report"]["trials"]) == len(GM12_ITEMS)
        assert all(record["valid"] is None for record in gm12_result["report"]["trials"])

        bus = EventBus()
        await _run_plugin(
            Gm23MatrixReasoningPlugin(bus), Topics.REQ_GM23_START, Topics.REQ_GM23_ANSWER,
            lambda plugin, reply: {"session_id": reply["session_id"],
                                   "selected_id": plugin._sessions[reply["session_id"]].correct_id, "timestamp_ms": 1}, 10,
        )

        def maze_answer(plugin, reply):
            session = plugin._sessions[reply["session_id"]]
            maze = session.mazes[session.index]
            start, finish = tuple(maze["start"]), tuple(maze["finish"])
            queue = collections.deque([start]); previous = {start: None}
            while queue:
                x, y = queue.popleft()
                if (x, y) == finish:
                    break
                for dx, dy, direction, _ in DIRS:
                    nxt = (x + dx, y + dy)
                    if not maze["walls"][y][x][direction] and nxt not in previous:
                        previous[nxt] = (x, y); queue.append(nxt)
            path = []; cursor = finish
            while cursor is not None:
                path.append(list(cursor)); cursor = previous[cursor]
            path.reverse()
            return {"session_id": reply["session_id"], "path": path, "boundary_errors": 0,
                    "planning_ms": 100, "execution_ms": 500, "timestamp_ms": 1}

        bus = EventBus()
        await _run_plugin(Gm19MazePlugin(bus), Topics.REQ_GM19_START, Topics.REQ_GM19_ANSWER, maze_answer, 3)

    asyncio.run(scenario())

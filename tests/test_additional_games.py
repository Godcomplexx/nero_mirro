from __future__ import annotations

import asyncio
import collections

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.gm01_pair_cards.plugin import Gm01PairCardsPlugin
from neuro_mirror.plugins.games.gm01_pair_cards.stimuli import STIMULI as GM01_STIMULI
from neuro_mirror.plugins.games.gm03_changed_object.plugin import Gm03ChangedObjectPlugin
from neuro_mirror.plugins.games.gm05_word_list.plugin import Gm05WordListPlugin
from neuro_mirror.plugins.games.gm08_stop_signal.plugin import Gm08StopSignalPlugin
from neuro_mirror.plugins.games.gm09_object_tracking.plugin import Gm09ObjectTrackingPlugin
from neuro_mirror.plugins.games.gm10_find_difference.plugin import Gm10FindDifferencePlugin
from neuro_mirror.plugins.games.gm11_serial_count.plugin import Gm11SerialCountPlugin
from neuro_mirror.plugins.games.gm12_word_picture.plugin import Gm12WordPicturePlugin
from neuro_mirror.plugins.games.gm12_word_picture.stimuli import ITEMS as GM12_ITEMS
from neuro_mirror.plugins.games.gm13_categories.plugin import Gm13CategoriesPlugin
from neuro_mirror.plugins.games.gm14_word_builder.plugin import Gm14WordBuilderPlugin
from neuro_mirror.plugins.games.gm14_word_builder.stimuli import WORD_SETS
from neuro_mirror.plugins.games.gm15_picture_naming.plugin import Gm15PictureNamingPlugin
from neuro_mirror.plugins.games.gm17_mental_rotation.plugin import Gm17MentalRotationPlugin
from neuro_mirror.plugins.games.gm17_mental_rotation.stimuli import SHAPE_SETS
from neuro_mirror.plugins.games.gm18_puzzle.plugin import Gm18PuzzlePlugin
from neuro_mirror.plugins.games.gm19_maze.plugin import DIRS, Gm19MazePlugin
from neuro_mirror.plugins.games.gm21_odd_one_out.plugin import Gm21OddOneOutPlugin
from neuro_mirror.plugins.games.gm23_matrix_reasoning.plugin import Gm23MatrixReasoningPlugin
from neuro_mirror.plugins.games.gm24_category_naming.plugin import Gm24CategoryNamingPlugin


def test_gm01_uses_the_selected_stimulus_set_for_every_board() -> None:
    plugin = Gm01PairCardsPlugin(EventBus())

    reply = plugin.start_game({"stimulus_set": "животные"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "животные"
    assert all(
        set(board).issubset(GM01_STIMULI["животные"])
        for board in session.boards
    )


def test_gm01_falls_back_to_a_known_stimulus_set() -> None:
    plugin = Gm01PairCardsPlugin(EventBus())

    reply = plugin.start_game({"stimulus_set": "неизвестный набор"})

    assert reply["stimulus_set"] == plugin.definition.stimulus_sets[0]


def test_gm03_uses_only_the_selected_room() -> None:
    plugin = Gm03ChangedObjectPlugin(EventBus())

    reply = plugin.start_game({"stimulus_set": "ванная"})

    assert reply["stimulus_set"] == "ванная"
    assert reply["room"] == "Ванная"
    assert reply["room_count"] == 1


def test_gm03_falls_back_to_the_first_room() -> None:
    plugin = Gm03ChangedObjectPlugin(EventBus())

    reply = plugin.start_game({"stimulus_set": "неизвестная комната"})

    assert reply["stimulus_set"] == plugin.definition.stimulus_sets[0]
    assert reply["room"] == "Кухня"


def test_gm05_uses_only_the_selected_word_set() -> None:
    plugin = Gm05WordListPlugin(EventBus())

    reply = plugin.start_game({"stimulus_set": "одежда"})

    assert reply["stimulus_set"] == "одежда"
    assert reply["category"] == "Одежда"
    assert reply["round_count"] == 1


def test_gm05_falls_back_to_the_first_word_set() -> None:
    plugin = Gm05WordListPlugin(EventBus())

    reply = plugin.start_game({"stimulus_set": "неизвестный список"})

    assert reply["stimulus_set"] == plugin.definition.stimulus_sets[0]
    assert reply["category"] == "Продукты питания"


def test_gm08_uses_the_selected_signal() -> None:
    reply = Gm08StopSignalPlugin(EventBus()).start_game(
        {"stimulus_set": "цифра 1"}
    )

    assert reply["stimulus_set"] == "цифра 1"
    assert reply["symbol"] == "1"


def test_gm09_uses_the_selected_object_shape_in_every_round() -> None:
    plugin = Gm09ObjectTrackingPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "силуэты птиц"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "силуэты птиц"
    assert {item["shape"] for item in session.rounds} == {"bird"}


def test_gm10_uses_only_the_selected_scene() -> None:
    reply = Gm10FindDifferencePlugin(EventBus()).start_game(
        {"stimulus_set": "магазин"}
    )

    assert reply["stimulus_set"] == "магазин"
    assert reply["scene"] == "Магазин"
    assert reply["scene_count"] == 1


def test_gm11_uses_only_the_selected_arithmetic_rule() -> None:
    reply = Gm11SerialCountPlugin(EventBus()).start_game(
        {"stimulus_set": "сложение"}
    )

    assert reply["stimulus_set"] == "сложение"
    assert reply["instruction"] == "Прибавляйте 3"
    assert reply["current"] == 5
    assert reply["rule_count"] == 1


def test_gm12_uses_only_the_selected_picture_category() -> None:
    plugin = Gm12WordPicturePlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "еда"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "еда"
    assert reply["category"] == "еда"
    assert reply["trial_count"] == 10
    assert {item[0] for item in session.order} == {"еда"}


def test_gm13_uses_only_the_selected_category() -> None:
    plugin = Gm13CategoriesPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "мебель"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "мебель"
    assert reply["category"] == "Мебель"
    assert reply["block_count"] == 1
    assert len(session.categories) == 1


def test_gm14_uses_only_the_selected_word_set() -> None:
    plugin = Gm14WordBuilderPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "еда и блюда", "difficulty_level": 2})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "еда и блюда"
    assert set(session.words).issubset(WORD_SETS["еда и блюда"])
    assert all(4 <= len(word) <= 8 for word in session.words)


def test_gm15_uses_only_the_selected_picture_category() -> None:
    plugin = Gm15PictureNamingPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "предметы быта"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "предметы быта"
    assert reply["category"] == "Предметы быта"
    assert {item["category"] for item in session.items} == {"Предметы быта"}


def test_gm17_uses_only_the_selected_shape_set() -> None:
    plugin = Gm17MentalRotationPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "силуэты предметов"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "силуэты предметов"
    assert set(session.shape_order).issubset(SHAPE_SETS["силуэты предметов"])
    assert len(session.shape_order) == 30


def test_gm18_uses_only_the_selected_puzzle_scene() -> None:
    plugin = Gm18PuzzlePlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "портрет"})

    assert reply["stimulus_set"] == "портрет"
    assert reply["name"] == "Магазин"
    assert reply["required_rounds"] == 1
    assert reply["image"].endswith("shop_a.png")


def test_gm21_uses_the_selected_main_category() -> None:
    plugin = Gm21OddOneOutPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "инструменты"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "инструменты"
    assert session.main_category == "Инструменты"
    assert session.current_trial["main_category"] == "Инструменты"
    assert sum(choice["category"] == "Инструменты" for choice in session.current_trial["choices"]) == 3


def test_gm23_uses_the_selected_answer_symbol() -> None:
    plugin = Gm23MatrixReasoningPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "сердце"})
    session = plugin._sessions[reply["session_id"]]
    correct = next(option for option in reply["options"] if option["id"] == session.correct_id)

    assert reply["stimulus_set"] == "сердце"
    assert correct["symbol"] == "heart"
    assert all((4 + offset) % 3 == 2 for offset in session.offsets)


def test_gm24_uses_only_the_selected_category() -> None:
    plugin = Gm24CategoryNamingPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "транспорт"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "транспорт"
    assert reply["trial_count"] == 2
    assert {trial["category"] for trial in session.trials} == {"Транспорт"}


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
            lambda plugin, reply: {"session_id": reply["session_id"], "selected": reply["study_words"], "timestamp_ms": 1}, 1,
        )

        bus = EventBus()
        await _run_plugin(
            Gm08StopSignalPlugin(bus), Topics.REQ_GM08_START, Topics.REQ_GM08_ANSWER,
            lambda plugin, reply: {"session_id": reply["session_id"], "responded": not reply["mirrored"],
                                   "reaction_ms": 300 if not reply["mirrored"] else None, "timestamp_ms": 1}, 40,
        )

        bus = EventBus()
        gm12_expected = sum(item[0] == "животные" for item in GM12_ITEMS)
        gm12_result = await _run_plugin(
            Gm12WordPicturePlugin(bus), Topics.REQ_GM12_START, Topics.REQ_GM12_ANSWER,
            lambda plugin, reply: {"session_id": reply["session_id"],
                                   "selected_word": plugin._sessions[reply["session_id"]].order[plugin._sessions[reply["session_id"]].index][1],
                                   "timestamp_ms": 1},
            gm12_expected,
        )
        assert gm12_result["checkpoint"]["next_index"] == gm12_expected
        assert len(gm12_result["report"]["trials"]) == gm12_expected
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

from __future__ import annotations

from neuro_mirror.plugins.games.catalog import get_game_definition

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
from neuro_mirror.plugins.games.gm16_phonemic_fluency.plugin import Gm16PhonemicFluencyPlugin
from neuro_mirror.plugins.games.gm17_mental_rotation.plugin import Gm17MentalRotationPlugin
from neuro_mirror.plugins.games.gm17_mental_rotation.stimuli import SHAPE_SETS
from neuro_mirror.plugins.games.gm18_puzzle.plugin import Gm18PuzzlePlugin
from neuro_mirror.plugins.games.gm19_maze.plugin import DIRS, Gm19MazePlugin
from neuro_mirror.plugins.games.gm19_maze.stimuli import MAZE_COUNT
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


def test_gm01_accepts_a_complete_pair_in_one_answer() -> None:
    plugin = Gm01PairCardsPlugin(EventBus())
    started = plugin.start_game({})
    cards = started["cards"]
    first = 0
    second = next(index for index, card in enumerate(cards[1:], start=1) if card == cards[first])

    reply = plugin.answer_game({
        "session_id": started["session_id"],
        "first_index": first,
        "selected_index": second,
        "reaction_ms": 10,
    })

    assert reply["correct"] is True
    assert reply.get("first_pick") is not True
    assert first in reply.get("matched", (first, second))
    assert second in reply.get("matched", (first, second))


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


def test_gm05_difficulty_controls_targets_choices_and_study_time() -> None:
    plugin = Gm05WordListPlugin(EventBus())

    for level, targets, choices, study_ms in ((1, 4, 8, 6000), (2, 6, 12, 7000), (3, 8, 16, 8000)):
        reply = plugin.start_game({"difficulty_level": level})
        assert reply["difficulty_level"] == level
        assert len(reply["study_words"]) == targets
        assert len(reply["choices"]) == choices
        assert reply["study_ms"] == study_ms


def test_gm08_uses_the_selected_signal() -> None:
    reply = Gm08StopSignalPlugin(EventBus()).start_game(
        {"stimulus_set": "цифра 1"}
    )

    assert reply["stimulus_set"] == "цифра 1"
    assert reply["symbol"] == "1"


def test_gm08_difficulty_controls_signal_timing() -> None:
    plugin = Gm08StopSignalPlugin(EventBus())

    for level, display_ms, trial_slot_ms in (
        (1, 1200, 1800),
        (2, 900, 1500),
        (3, 650, 1200),
    ):
        reply = plugin.start_game({"difficulty_level": level})
        assert reply["difficulty_level"] == level
        assert reply["display_ms"] == display_ms
        assert reply["trial_slot_ms"] == trial_slot_ms


def test_gm09_uses_the_selected_object_shape_in_every_round() -> None:
    plugin = Gm09ObjectTrackingPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "силуэты птиц"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "силуэты птиц"
    assert {item["shape"] for item in session.rounds} == {"bird"}


def test_gm10_uses_all_scenes_for_selected_difficulty() -> None:
    plugin = Gm10FindDifferencePlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "магазин", "difficulty_level": 3})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "магазин"
    assert reply["scene"] == "Магазин"
    assert reply["scene_count"] == 3
    assert {scene["name"] for scene in session.scenes} == {"Магазин", "Станция", "Мастерская"}


def test_gm11_uses_only_the_selected_arithmetic_rule() -> None:
    reply = Gm11SerialCountPlugin(EventBus()).start_game(
        {"stimulus_set": "сложение"}
    )

    assert reply["stimulus_set"] == "сложение"
    assert reply["instruction"] == "Прибавляйте 3"
    assert reply["current"] == 5
    assert reply["rule_count"] == 1


def test_gm11_difficulty_controls_operation_switches() -> None:
    plugin = Gm11SerialCountPlugin(EventBus())

    expectations = {
        1: ([5], ["сложение"]),
        2: ([5, 5], ["сложение", "вычитание"]),
        3: ([3, 2, 3, 2], ["сложение", "вычитание", "сложение", "вычитание"]),
    }
    for level, (counts, rule_names) in expectations.items():
        reply = plugin.start_game({"stimulus_set": "сложение", "difficulty_level": level})
        session = plugin._sessions[reply["session_id"]]
        assert reply["difficulty_level"] == level
        assert reply["required_correct"] == counts[0]
        assert session.block_correct_counts == counts
        assert [rule["stimulus_set"] for rule in session.rules] == rule_names


def test_gm12_uses_only_the_selected_picture_category() -> None:
    plugin = Gm12WordPicturePlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "еда"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "еда"
    assert reply["category"] == "еда"
    assert reply["trial_count"] == 30
    assert {item[0] for item in session.order} == {"еда"}


def test_gm12_difficulty_controls_category_switching() -> None:
    plugin = Gm12WordPicturePlugin(EventBus())

    easy = plugin.start_game({"stimulus_set": "еда", "difficulty_level": 1})
    easy_categories = [item[0] for item in plugin._sessions[easy["session_id"]].order]
    assert easy_categories == ["еда"] * 30

    medium = plugin.start_game({"stimulus_set": "еда", "difficulty_level": 2})
    medium_categories = [item[0] for item in plugin._sessions[medium["session_id"]].order]
    assert medium_categories == ["еда"] * 15 + ["животные"] * 15

    hard = plugin.start_game({"stimulus_set": "еда", "difficulty_level": 3})
    hard_categories = [item[0] for item in plugin._sessions[hard["session_id"]].order]
    assert hard_categories == ["еда", "животные", "предметы быта"] * 10


def test_gm13_uses_only_the_selected_category() -> None:
    plugin = Gm13CategoriesPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "мебель"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "мебель"
    assert reply["category"] == "Мебель"
    assert reply["block_count"] == 1
    assert len(session.categories) == 1


def test_gm13_difficulty_controls_category_blocks() -> None:
    plugin = Gm13CategoriesPlugin(EventBus())
    expected_counts = {1: 1, 2: 2, 3: 3}

    for level, expected_count in expected_counts.items():
        reply = plugin.start_game({"stimulus_set": "мебель", "difficulty_level": level})
        session = plugin._sessions[reply["session_id"]]
        categories = [category["name"] for category in session.categories]
        assert reply["difficulty_level"] == level
        assert reply["block_count"] == expected_count
        assert reply["duration_ms"] == 20_000
        assert categories[0] == "Мебель"
        assert len(categories) == len(set(categories)) == expected_count


def test_gm13_randomly_selects_a_category_when_none_is_requested() -> None:
    plugin = Gm13CategoriesPlugin(EventBus())

    reply = plugin.start_game({"difficulty_level": 1})

    assert reply["stimulus_set"] in {"овощи", "животные", "мебель"}
    assert reply["category"].casefold() == reply["stimulus_set"]


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
    assert len(session.items) == 30


def test_gm15_difficulty_controls_category_switching() -> None:
    plugin = Gm15PictureNamingPlugin(EventBus())

    medium = plugin.start_game({"stimulus_set": "животные", "difficulty_level": 2})
    medium_categories = [item["category"] for item in plugin._sessions[medium["session_id"]].items]
    assert medium_categories[:15] == ["Животные"] * 15
    assert len(set(medium_categories[15:])) == 1
    assert medium_categories[15] != "Животные"
    assert len(medium_categories) == 30

    hard = plugin.start_game({"stimulus_set": "животные", "difficulty_level": 3})
    hard_categories = [item["category"] for item in plugin._sessions[hard["session_id"]].items]
    assert hard_categories[::3] == ["Животные"] * 10
    assert len(set(hard_categories)) == 3
    assert len(hard_categories) == 30


def test_gm16_difficulty_controls_letter_productivity() -> None:
    plugin = Gm16PhonemicFluencyPlugin(EventBus())
    pools = {
        1: set("ПСКОВР"),
        2: set("МБДТНГЗИАУЛ"),
        3: set("ФШЧЭХЖЦ"),
    }

    for level, letters in pools.items():
        reply = plugin.start_game({"difficulty_level": level})
        assert reply["difficulty_level"] == level
        assert reply["letter"] in letters
        assert reply["recording_ms"] == 300_000


def test_gm17_uses_only_the_selected_shape_set() -> None:
    plugin = Gm17MentalRotationPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "силуэты предметов"})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "силуэты предметов"
    assert set(session.shape_order).issubset(SHAPE_SETS["силуэты предметов"])
    assert len(session.shape_order) == 30


def test_gm18_uses_all_puzzle_scenes_for_selected_difficulty() -> None:
    plugin = Gm18PuzzlePlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "портрет", "difficulty_level": 3})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "портрет"
    assert reply["required_rounds"] == 3
    assert reply["rows"] == 4
    assert reply["columns"] == 5
    assert reply["difficulty_parameters"] == {
        "pieces": 20,
        "grid": "5×4",
        "puzzles": 3,
    }
    assert {puzzle["image"] for puzzle in session.puzzles} == {
        "shop_a.png",
        "station_hard_01_a.png",
        "workshop_hard_02_a.png",
    }


def test_gm18_keeps_a_wrong_piece_in_the_pool_and_fixes_a_correct_one() -> None:
    plugin = Gm18PuzzlePlugin(EventBus())
    started = plugin.start_game({"difficulty_level": 1})
    piece = started["pieces"][0]
    wrong_target = (piece + 1) % len(started["placements"])

    rejected = plugin.answer_game({
        "session_id": started["session_id"],
        "piece_id": piece,
        "target_index": wrong_target,
    })
    assert rejected["placement_correct"] is False
    assert piece in rejected["pieces"]
    assert rejected["placements"][wrong_target] is None

    accepted = plugin.answer_game({
        "session_id": started["session_id"],
        "piece_id": piece,
        "target_index": piece,
    })
    assert accepted["placement_correct"] is True
    assert piece not in accepted["pieces"]
    assert accepted["placements"][piece] == piece


def test_gm21_uses_the_selected_main_category() -> None:
    plugin = Gm21OddOneOutPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "инструменты", "difficulty_level": 1})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "инструменты"
    assert reply["difficulty_level"] == 1
    assert reply["required_trials"] == 30
    assert session.main_category == "Инструменты"
    assert session.current_trial["main_category"] == "Инструменты"
    assert sum(choice["category"] == "Инструменты" for choice in session.current_trial["choices"]) == 3


def test_gm23_uses_the_selected_answer_symbol() -> None:
    plugin = Gm23MatrixReasoningPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "сердце", "difficulty_level": 1})
    session = plugin._sessions[reply["session_id"]]
    correct = next(option for option in reply["options"] if option["id"] == session.correct_id)

    assert reply["stimulus_set"] == "сердце"
    assert reply["difficulty_level"] == 1
    assert reply["trial_count"] == 18
    assert len(reply["options"]) == 4
    assert correct["symbol"] == "heart"
    assert all((4 + offset) % 3 == 2 for offset in session.offsets)


def test_gm24_uses_selected_category_first_and_applies_difficulty() -> None:
    plugin = Gm24CategoryNamingPlugin(EventBus())
    reply = plugin.start_game({"stimulus_set": "транспорт", "difficulty_level": 1})
    session = plugin._sessions[reply["session_id"]]

    assert reply["stimulus_set"] == "транспорт"
    assert reply["difficulty_level"] == 1
    assert reply["trial_count"] == 12
    assert len(reply["words"]) == 2
    assert all(len(trial["words"]) == 2 for trial in session.trials)
    assert session.trials[0]["category"] == "Транспорт"
    assert len({trial["category"] for trial in session.trials}) == 2


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
            Gm05WordListPlugin(bus), get_game_definition("GM-05").start_request_topic, get_game_definition("GM-05").answer_request_topic,
            lambda plugin, reply: {"session_id": reply["session_id"], "selected": reply["study_words"], "timestamp_ms": 1}, 1,
        )

        bus = EventBus()
        await _run_plugin(
            Gm08StopSignalPlugin(bus), get_game_definition("GM-08").start_request_topic, get_game_definition("GM-08").answer_request_topic,
            lambda plugin, reply: {"session_id": reply["session_id"], "responded": not reply["mirrored"],
                                   "reaction_ms": 300 if not reply["mirrored"] else None, "timestamp_ms": 1}, 40,
        )

        bus = EventBus()
        gm12_expected = sum(item[0] == "животные" for item in GM12_ITEMS)
        gm12_result = await _run_plugin(
            Gm12WordPicturePlugin(bus), get_game_definition("GM-12").start_request_topic, get_game_definition("GM-12").answer_request_topic,
            lambda plugin, reply: {"session_id": reply["session_id"],
                                   "selected_word": plugin._sessions[reply["session_id"]].order[plugin._sessions[reply["session_id"]].index][1],
                                   "timestamp_ms": 1},
            gm12_expected,
        )
        assert gm12_result["checkpoint"]["next_index"] == gm12_expected
        assert len(gm12_result["report"]["trials"]) == gm12_expected
        assert all(record["valid"] is True for record in gm12_result["report"]["trials"])

        bus = EventBus()
        await _run_plugin(
            Gm23MatrixReasoningPlugin(bus), get_game_definition("GM-23").start_request_topic, get_game_definition("GM-23").answer_request_topic,
            lambda plugin, reply: {"session_id": reply["session_id"],
                                   "selected_id": plugin._sessions[reply["session_id"]].correct_id, "timestamp_ms": 1}, 18,
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
        # Число лабиринтов берётся из набора стимулов, а не задаётся числом:
        # при изменении набора ожидание в тесте разошлось бы молча.
        await _run_plugin(Gm19MazePlugin(bus), get_game_definition("GM-19").start_request_topic, get_game_definition("GM-19").answer_request_topic, maze_answer, MAZE_COUNT)

    asyncio.run(scenario())

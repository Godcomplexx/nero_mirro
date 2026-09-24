from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from neuro_mirror.plugins.games.catalog import GAME_CATALOG, get_game_definition
from neuro_mirror.plugins.games.contracts import (
    Domain,
    GameDefinition,
    Modality,
    ResponseType,
)
from neuro_mirror.plugins.games.registry import (
    discover_game_registrations,
    implemented_game_codes,
)
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.plugins.games.history import GameHistoryStore
from neuro_mirror.plugins.games.selector import Presentation, select_game


def test_catalog_contains_all_spreadsheet_forms() -> None:
    assert len(GAME_CATALOG) == 24
    assert {item.code for item in GAME_CATALOG} == {
        f"GM-{index:02d}" for index in range(1, 25)
    }
    assert get_game_definition("gm19").primary_domain == Domain.ABSTRACTION
    assert get_game_definition("gm14_word_builder").primary_domain == Domain.SPEECH


def test_plugin_can_define_a_game_outside_initial_catalog() -> None:
    class CustomGame(BrowserGamePlugin):
        game_code = "GM-CUSTOM-99"
        game_definition = GameDefinition(
            code=game_code,
            slug="custom_game",
            title="Пользовательская игра",
            domains=(Domain.MEMORY,),
            mechanics=("custom",),
            modalities=(Modality.VISUAL,),
            response_type=ResponseType.CLICK,
            stimulus_sets=("set-1",),
        )

    plugin = CustomGame(EventBus())
    assert plugin.definition.code == "GM-CUSTOM-99"


def test_registry_discovers_current_plugins_without_runtime_imports() -> None:
    registrations = discover_game_registrations()
    assert len(registrations) == 10
    assert all(issubclass(item.plugin_class, BrowserGamePlugin) for item in registrations)
    assert implemented_game_codes() == {
        "GM-02", "GM-05", "GM-07", "GM-08", "GM-12",
        "GM-14", "GM-17", "GM-19", "GM-20", "GM-23",
    }
    for registration in registrations:
        package = __import__(registration.package_name, fromlist=["__path__"])
        folder = next(iter(package.__path__))
        assert (Path(folder) / "plugin.py").is_file()
        assert (Path(folder) / "stimuli.py").is_file()
        assert (Path(folder) / "web.js").is_file()


def test_selector_does_not_repeat_form_and_prefers_new_mechanic() -> None:
    now = datetime.now(UTC)
    history = (
        Presentation(
            game_code="GM-02",
            mechanics=("spatial_sequence_recall",),
            modalities=(Modality.VISUAL,),
            stimulus_set="квадраты",
            presented_at=now - timedelta(days=1),
        ),
    )
    decision = select_game(
        Domain.MEMORY,
        session_game_codes=frozenset({"GM-02"}),
        history=history,
        available_codes=frozenset({"GM-02", "GM-05"}),
    )
    assert decision.game.code == "GM-05"
    assert decision.game.primary_domain == Domain.MEMORY
    assert "форма не повторяется в занятии" in decision.reasons


def test_selector_accepts_future_game_definitions() -> None:
    custom = GameDefinition(
        code="GM-FUTURE-01",
        slug="future_game",
        title="Будущая игра",
        domains=(Domain.MEMORY,),
        mechanics=("new_mechanic",),
        modalities=(Modality.VISUAL,),
        response_type=ResponseType.CLICK,
        stimulus_sets=("future-set",),
    )
    decision = select_game(
        Domain.MEMORY,
        available_codes=frozenset({custom.code}),
        definitions=(custom,),
    )
    assert decision.game.code == custom.code
    assert decision.stimulus_set == "future-set"


def test_presentation_history_round_trip(tmp_path) -> None:
    store = GameHistoryStore(tmp_path / "history.json")
    store.record(
        user_id="user-1",
        session_id="session-1",
        game_code="GM-07",
        stimulus_set="буква Т",
        difficulty_level=1,
    )
    history = GameHistoryStore(tmp_path / "history.json").for_user("user-1")
    assert len(history) == 1
    assert history[0].game_code == "GM-07"
    assert history[0].mechanics == ("conjunction_visual_search",)

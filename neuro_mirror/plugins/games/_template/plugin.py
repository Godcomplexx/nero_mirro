"""Template scenario for a catalogued browser game."""
from __future__ import annotations

from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.contracts import (
    Domain,
    GameDefinition,
    Modality,
    ResponseType,
)
from neuro_mirror.plugins.games.trial_journal import TrialJournal


class TemplateGamePlugin(BrowserGamePlugin):
    plugin_name = "replace_me"
    game_code = "GM-CUSTOM-01"
    # Required only when game_code is absent from the initial Excel catalog.
    game_definition = GameDefinition(
        code=game_code,
        slug=plugin_name,
        title="Название игры",
        domains=(Domain.MEMORY,),
        mechanics=("mechanic_code",),
        modalities=(Modality.VISUAL,),
        response_type=ResponseType.CLICK,
        stimulus_sets=("stimulus_set_1",),
    )

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, object] = {}

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Create the session, choose a stimulus set and start active timing.
        # journal = TrialJournal(game_id=self.game_code, session_id=session_id)
        raise NotImplementedError

    def answer_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Record the first answer before feedback. Return a checkpoint after
        # every assessed unit and a report-compatible result on completion.
        raise NotImplementedError

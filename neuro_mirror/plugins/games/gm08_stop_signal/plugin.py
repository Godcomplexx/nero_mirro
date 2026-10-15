from __future__ import annotations
import secrets, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm08_stop_signal.stimuli import SIGNALS, TRIAL_COUNT
from neuro_mirror.screening.gm08_scoring import score_gm08_trials
@dataclass(slots=True)
class StopSession:
    session_id: str; schedule: list[bool]; stimulus_set: str; symbol: str
    difficulty_level: int; difficulty_parameters: dict[str, Any]
    index: int = 0; trials: list[dict[str, Any]] = field(default_factory=list)

class Gm08StopSignalPlugin(BrowserGamePlugin):
    plugin_name = "gm08_stop_signal"
    game_code = "GM-08"
    def __init__(self, bus): super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def start_game(self, payload):
        return self._start(
            stimulus_set=str(payload.get("stimulus_set") or ""),
            difficulty_level=payload.get("difficulty_level"),
            rng=self._session_random(payload),
        )
    def _start(self, *, stimulus_set="", difficulty_level=None, rng=None):
        rng = rng or self._random
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        available = tuple(name for name in self.definition.stimulus_sets if name in SIGNALS) or tuple(SIGNALS)
        selected = stimulus_set if stimulus_set in available else available[0]
        schedule = [False] * 30 + [True] * 10; rng.shuffle(schedule)
        s = StopSession(
            uuid.uuid4().hex, schedule, selected, SIGNALS[selected], level, parameters
        ); self._sessions[s.session_id] = s; return self._payload(s)
    def _payload(self, s):
        return {"ok": True, "finished": False, "session_id": s.session_id, "trial": s.index + 1,
                "trial_count": TRIAL_COUNT,
                "difficulty_level": s.difficulty_level,
                "difficulty_parameters": dict(s.difficulty_parameters),
                "display_ms": int(s.difficulty_parameters["display_ms"]),
                "trial_slot_ms": int(s.difficulty_parameters["trial_slot_ms"]),
                "stimulus_set": s.stimulus_set,
                "symbol": s.symbol, "mirrored": s.schedule[s.index]}
    def _resume(self, s, paused_ms):
        """Прерванный сигнал предъявляется снова (4.5, п. 5)."""
        return self._payload(s)
    def _trial_number(self, s):
        return s.index + 1
    def _answer(self, payload):
        s = self._sessions.get(str(payload.get("session_id") or ""))
        if s is None: return {"ok": False, "message": "Игровая сессия не найдена."}
        responded = payload.get("responded")
        if not isinstance(responded, bool): return {"ok": False, "message": "Некорректный ответ."}
        stop = s.schedule[s.index]; rt = payload.get("reaction_ms")
        s.trials.append({"trial": s.index + 1, "stop_signal": stop, "responded": responded,
                         "correct": (not responded) if stop else responded, "reaction_ms": rt,
                         "client_timestamp_ms": payload.get("timestamp_ms")})
        s.index += 1
        if s.index == TRIAL_COUNT:
            self._sessions.pop(s.session_id, None)
            return {"ok": True, "finished": True, "metrics": score_gm08_trials(s.trials), "events": s.trials}
        return self._payload(s)

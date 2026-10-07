from __future__ import annotations
import secrets, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm08_stop_signal.stimuli import SIGNALS, TRIAL_COUNT
from neuro_mirror.screening.gm08_scoring import score_gm08_trials
@dataclass(slots=True)
class StopSession:
    session_id: str; schedule: list[bool]; stimulus_set: str; symbol: str
    index: int = 0; trials: list[dict[str, Any]] = field(default_factory=list)

class Gm08StopSignalPlugin(BrowserGamePlugin):
    plugin_name = "gm08_stop_signal"
    game_code = "GM-08"
    def __init__(self, bus): super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def start_game(self, payload):
        return self._start(stimulus_set=str(payload.get("stimulus_set") or ""))
    def _start(self, *, stimulus_set=""):
        available = tuple(name for name in self.definition.stimulus_sets if name in SIGNALS) or tuple(SIGNALS)
        selected = stimulus_set if stimulus_set in available else available[0]
        schedule = [False] * 30 + [True] * 10; self._random.shuffle(schedule)
        s = StopSession(uuid.uuid4().hex, schedule, selected, SIGNALS[selected]); self._sessions[s.session_id] = s; return self._payload(s)
    def _payload(self, s):
        return {"ok": True, "finished": False, "session_id": s.session_id, "trial": s.index + 1,
                "trial_count": TRIAL_COUNT, "display_ms": 1000, "stimulus_set": s.stimulus_set,
                "symbol": s.symbol, "mirrored": s.schedule[s.index]}
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

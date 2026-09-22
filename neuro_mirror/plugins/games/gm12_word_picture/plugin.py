from __future__ import annotations
import secrets, time, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm12_word_picture.stimuli import DISTRACTORS, ITEMS
from neuro_mirror.screening.gm12_scoring import score_gm12_trials

@dataclass(slots=True)
class PictureSession:
    session_id: str; order: list[tuple[str, str, str]]; index: int = 0
    shown_at_ms: float = 0.0; choices: list[str] = field(default_factory=list); trials: list[dict[str, Any]] = field(default_factory=list)

class Gm12WordPicturePlugin(BrowserGamePlugin):
    plugin_name = "gm12_word_picture"
    game_code = "GM-12"
    def __init__(self, bus) -> None:
        super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def _start(self):
        order = list(ITEMS); self._random.shuffle(order)
        session_id = uuid.uuid4().hex
        session = PictureSession(session_id, order)
        self._sessions[session.session_id] = session
        return self._payload(session)
    def _payload(self, session):
        category, word, picture = session.order[session.index]
        pool = [item for item in DISTRACTORS[category] if item != word]; self._random.shuffle(pool)
        session.choices = [word] + pool[:3]; self._random.shuffle(session.choices); session.shown_at_ms = time.time() * 1000
        return {"ok": True, "finished": False, "session_id": session.session_id, "trial": session.index + 1,
                "trial_count": len(session.order), "category": category, "picture": picture, "choices": session.choices}
    def _answer(self, payload):
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None: return {"ok": False, "message": "Игровая сессия не найдена."}
        selected = str(payload.get("selected_word") or ""); category, word, picture = session.order[session.index]
        elapsed_ms = max(0.0, time.time() * 1000 - session.shown_at_ms)
        valid = selected in session.choices
        if not valid: return {"ok": False, "message": "Некорректный ответ."}
        session.trials.append({"trial": session.index + 1, "category": category, "target_word": word, "picture": picture,
                               "choices": session.choices, "selected_word": selected, "correct": selected == word,
                               "reaction_ms": elapsed_ms, "client_timestamp_ms": payload.get("timestamp_ms")})
        session.index += 1
        if session.index == len(session.order):
            self._sessions.pop(session.session_id, None)
            metrics = score_gm12_trials(session.trials)
            return {"ok": True, "finished": True, "metrics": metrics, "events": session.trials}
        return self._payload(session)

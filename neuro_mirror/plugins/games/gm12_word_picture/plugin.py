from __future__ import annotations
import secrets, time, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm12_word_picture.stimuli import DISTRACTORS, ITEMS
from neuro_mirror.screening.gm12_scoring import score_gm12_trials

@dataclass(slots=True)
class PictureSession:
    session_id: str; order: list[tuple[str, str, str]]; stimulus_set: str; index: int = 0
    difficulty_level: int = 1; difficulty_parameters: dict[str, Any] = field(default_factory=dict)
    shown_at_ms: float = 0.0
    choices: list[str] = field(default_factory=list); trials: list[dict[str, Any]] = field(default_factory=list)

class Gm12WordPicturePlugin(BrowserGamePlugin):
    plugin_name = "gm12_word_picture"
    game_code = "GM-12"
    def __init__(self, bus) -> None:
        super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def start_game(self, payload):
        return self._start(
            stimulus_set=str(payload.get("stimulus_set") or ""),
            difficulty_level=payload.get("difficulty_level"),
        )
    def _start(self, *, stimulus_set="", difficulty_level=None):
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        categories = tuple(dict.fromkeys(category for category, _, _ in ITEMS))
        available = tuple(name for name in self.definition.stimulus_sets if name in categories) or categories
        selected = stimulus_set if stimulus_set in available else available[0]
        ordered_categories = [selected] + [name for name in available if name != selected]
        active_categories = ordered_categories[:int(parameters["category_count"])]
        queues = {category: [item for item in ITEMS if item[0] == category] for category in active_categories}
        for queue in queues.values(): self._random.shuffle(queue)
        trial_count = int(parameters["trials"])
        switch_every = int(parameters["switch_every"])
        if switch_every <= 0:
            category_order = [active_categories[0]] * trial_count
        else:
            category_order = [
                active_categories[(index // switch_every) % len(active_categories)]
                for index in range(trial_count)
            ]
        order = [queues[category].pop() for category in category_order]
        session_id = uuid.uuid4().hex
        session = PictureSession(
            session_id,
            order,
            selected,
            difficulty_level=level,
            difficulty_parameters=parameters,
        )
        self._sessions[session.session_id] = session
        return self._payload(session)
    def _payload(self, session):
        category, word, picture = session.order[session.index]
        pool = [item for item in DISTRACTORS[category] if item != word]; self._random.shuffle(pool)
        session.choices = [word] + pool[:3]; self._random.shuffle(session.choices); session.shown_at_ms = time.time() * 1000
        return {"ok": True, "finished": False, "session_id": session.session_id, "trial": session.index + 1,
                "trial_count": len(session.order),
                "stimulus_set": session.stimulus_set,
                "difficulty_level": session.difficulty_level,
                "difficulty_parameters": dict(session.difficulty_parameters),
                "category": category, "picture": picture, "choices": session.choices}
    def _answer(self, payload):
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None: return {"ok": False, "message": "Игровая сессия не найдена."}
        selected = str(payload.get("selected_word") or ""); category, word, picture = session.order[session.index]
        elapsed_ms = max(0.0, time.time() * 1000 - session.shown_at_ms)
        valid = selected in session.choices
        if not valid: return {"ok": False, "message": "Некорректный ответ."}
        correct = selected == word
        session.trials.append({"trial": session.index + 1, "category": category, "target_word": word, "picture": picture,
                               "choices": session.choices, "selected_word": selected, "correct": correct,
                               "reaction_ms": elapsed_ms, "client_timestamp_ms": payload.get("timestamp_ms")})
        session.index += 1
        all_done = session.index == len(session.order)
        if all_done:
            result = self._finish(session)
            result["correct"] = correct
            return result
        result = self._payload(session)
        result["previous_correct"] = correct
        return result

    def _finish(self, session):
        self._sessions.pop(session.session_id, None)
        metrics = score_gm12_trials(session.trials, expected_trials=len(session.trials))
        return {"ok": True, "finished": True, "completion_reason": "all_items",
                "metrics": metrics, "events": session.trials}

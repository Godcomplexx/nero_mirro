from __future__ import annotations
import secrets, time, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm23_matrix_reasoning.stimuli import STYLES, SYMBOLS
from neuro_mirror.screening.gm23_scoring import score_gm23_trials
@dataclass(slots=True)
class MatrixSession:
    session_id: str; offsets: list[int]; stimulus_set: str; difficulty_level: int; difficulty_parameters: dict[str, Any]
    pattern_mode: str; style_count: int; option_count: int; index: int = 0; correct_id: str = ""; shown_at_ms: float = 0.0
    current: dict[str, Any] = field(default_factory=dict); trials: list[dict[str, Any]] = field(default_factory=list)
class Gm23MatrixReasoningPlugin(BrowserGamePlugin):
    plugin_name = "gm23_matrix_reasoning"
    game_code = "GM-23"
    def __init__(self, bus): super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start(stimulus_set=str(payload.get("stimulus_set") or ""), difficulty_level=payload.get("difficulty_level"))
    def _start(self, *, stimulus_set: str = "", difficulty_level: object = None):
        config=level_config(self.game_code)
        try:level=int(difficulty_level or config["default_level"])
        except (TypeError,ValueError):level=int(config["default_level"])
        available_levels={int(item["level"]):item for item in config["levels"]}
        if level not in available_levels:level=int(config["default_level"])
        parameters=dict(available_levels[level]["parameters"]);trial_count=int(parameters["trials"]);mode=str(parameters["pattern_mode"]);style_count=int(parameters["style_count"]);option_count=int(parameters["option_count"])
        symbol_by_set={"звезда":"star","треугольник":"triangle","сердце":"heart"}; available=tuple(name for name in self.definition.stimulus_sets if name in symbol_by_set); selected=stimulus_set if stimulus_set in available else self._random.choice(available);target_index=SYMBOLS.index(symbol_by_set[selected]);first_offset=target_index if mode=="dual_axis" else (target_index-4)%len(SYMBOLS);offsets=[first_offset+len(SYMBOLS)*index for index in range(trial_count)];self._random.shuffle(offsets);s=MatrixSession(uuid.uuid4().hex,offsets,selected,level,parameters,mode,style_count,option_count);self._sessions[s.session_id]=s;return self._payload(s)
    @staticmethod
    def _cell(mode,r,c,offset):
        if mode=="symbol_only":return {"symbol":SYMBOLS[(r+c+offset)%3],"style":"filled"}
        if mode=="dual_axis":return {"symbol":SYMBOLS[(r+2*c+offset)%3],"style":STYLES[(2*r+c+offset//3)%2]}
        return {"symbol":SYMBOLS[(r+c+offset)%3],"style":STYLES[(r+c+offset//3)%2]}
    def _payload(self,s):
        offset=s.offsets[s.index]; cells=[]
        for r in range(3):
            for c in range(3):
                cells.append(None if (r,c)==(2,2) else self._cell(s.pattern_mode,r,c,offset))
        correct=self._cell(s.pattern_mode,2,2,offset)
        combos=[{"symbol":symbol,"style":style} for symbol in SYMBOLS for style in STYLES[:s.style_count] if {"symbol":symbol,"style":style}!=correct]
        self._random.shuffle(combos); options=[{"id":uuid.uuid4().hex,**correct}]+[{"id":uuid.uuid4().hex,**x} for x in combos[:s.option_count-1]]; self._random.shuffle(options)
        s.correct_id=next(x["id"] for x in options if x["symbol"]==correct["symbol"] and x["style"]==correct["style"])
        s.current={"matrix":cells,"options":options}; s.shown_at_ms=time.time()*1000
        return {"ok":True,"finished":False,"session_id":s.session_id,"stimulus_set":s.stimulus_set,"difficulty_level":s.difficulty_level,"difficulty_parameters":dict(s.difficulty_parameters),"trial":s.index+1,"trial_count":len(s.offsets),**s.current}
    def _answer(self,payload):
        s=self._sessions.get(str(payload.get("session_id") or ""))
        if s is None:return {"ok":False,"message":"Игровая сессия не найдена."}
        selected=str(payload.get("selected_id") or ""); valid={x["id"] for x in s.current["options"]}
        if selected not in valid:return {"ok":False,"message":"Некорректный ответ."}
        s.trials.append({"trial":s.index+1,**s.current,"selected_id":selected,"correct":selected==s.correct_id,"reaction_ms":max(0,time.time()*1000-s.shown_at_ms)})
        s.index+=1
        if s.index==len(s.offsets):
            self._sessions.pop(s.session_id,None); return {"ok":True,"finished":True,"metrics":score_gm23_trials(s.trials,expected_trials=len(s.offsets)),"events":s.trials}
        return self._payload(s)

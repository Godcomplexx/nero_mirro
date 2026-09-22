from __future__ import annotations
import secrets, time, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm23_matrix_reasoning.stimuli import STYLES, SYMBOLS, TRIAL_COUNT
from neuro_mirror.screening.gm23_scoring import score_gm23_trials
@dataclass(slots=True)
class MatrixSession:
    session_id: str; offsets: list[int]; index: int = 0; correct_id: str = ""; shown_at_ms: float = 0.0
    current: dict[str, Any] = field(default_factory=dict); trials: list[dict[str, Any]] = field(default_factory=list)
class Gm23MatrixReasoningPlugin(BrowserGamePlugin):
    plugin_name = "gm23_matrix_reasoning"
    game_code = "GM-23"
    def __init__(self, bus): super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def _start(self):
        offsets=list(range(TRIAL_COUNT)); self._random.shuffle(offsets); s=MatrixSession(uuid.uuid4().hex, offsets); self._sessions[s.session_id]=s; return self._payload(s)
    def _payload(self,s):
        offset=s.offsets[s.index]; cells=[]
        for r in range(3):
            for c in range(3):
                cells.append(None if (r,c)==(2,2) else {"symbol":SYMBOLS[(r+c+offset)%3],"style":STYLES[(r+c+offset//3)%2]})
        correct={"symbol":SYMBOLS[(4+offset)%3],"style":STYLES[(4+offset//3)%2]}
        combos=[{"symbol":symbol,"style":style} for symbol in SYMBOLS for style in STYLES if {"symbol":symbol,"style":style}!=correct]
        self._random.shuffle(combos); options=[{"id":uuid.uuid4().hex,**correct}]+[{"id":uuid.uuid4().hex,**x} for x in combos[:3]]; self._random.shuffle(options)
        s.correct_id=next(x["id"] for x in options if x["symbol"]==correct["symbol"] and x["style"]==correct["style"])
        s.current={"matrix":cells,"options":options}; s.shown_at_ms=time.time()*1000
        return {"ok":True,"finished":False,"session_id":s.session_id,"trial":s.index+1,"trial_count":TRIAL_COUNT,**s.current}
    def _answer(self,payload):
        s=self._sessions.get(str(payload.get("session_id") or ""))
        if s is None:return {"ok":False,"message":"Игровая сессия не найдена."}
        selected=str(payload.get("selected_id") or ""); valid={x["id"] for x in s.current["options"]}
        if selected not in valid:return {"ok":False,"message":"Некорректный ответ."}
        s.trials.append({"trial":s.index+1,**s.current,"selected_id":selected,"correct":selected==s.correct_id,"reaction_ms":max(0,time.time()*1000-s.shown_at_ms)})
        s.index+=1
        if s.index==TRIAL_COUNT:
            self._sessions.pop(s.session_id,None); return {"ok":True,"finished":True,"metrics":score_gm23_trials(s.trials),"events":s.trials}
        return self._payload(s)

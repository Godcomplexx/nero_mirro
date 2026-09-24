from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm10_find_difference.stimuli import SCENES
from neuro_mirror.screening.gm10_scoring import score_gm10


@dataclass(slots=True)
class DifferenceSession:
    session_id: str
    scene_index: int = 0
    found: set[int] = field(default_factory=set)
    shown_ms: float = field(default_factory=lambda: time.time()*1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm10FindDifferencePlugin(BrowserGamePlugin):
    plugin_name="gm10_find_difference"; game_code="GM-10"; start_handler="_start"; answer_handler="_answer"
    def __init__(self,bus): super().__init__(bus); self._sessions={}
    def _start(self):
        session=DifferenceSession(uuid.uuid4().hex);self._sessions[session.session_id]=session;return self._payload(session)
    def _answer(self,payload):
        session=self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:return {"ok":False,"message":"Игровая сессия не найдена."}
        x,y=float(payload.get("x",-1)),float(payload.get("y",-1));scene=SCENES[session.scene_index]
        hit=next((i for i,(dx,dy) in enumerate(scene["differences"]) if i not in session.found and math.dist((x,y),(dx,dy))<=scene["radius"]),None)
        correct=hit is not None
        if correct:session.found.add(hit)
        session.round_events.append({"scene":scene["name"],"clicks":[x,y],"difference_id":hit,"correct":correct,"reaction_ms":max(0,time.time()*1000-session.shown_ms)})
        scene_complete=len(session.found)==len(scene["differences"])
        if scene_complete:
            session.scene_index+=1;session.found=set();session.shown_ms=time.time()*1000
            if session.scene_index==len(SCENES):
                events=list(session.round_events);self._sessions.pop(session.session_id,None)
                return {"ok":True,"finished":True,"correct":True,"events":events,"metrics":score_gm10(events,sum(len(s["differences"]) for s in SCENES))}
        result=self._payload(session);result.update({"correct":correct,"hit":hit,"scene_complete":scene_complete});return result
    def _payload(self,session):
        scene=SCENES[session.scene_index]
        return {"ok":True,"finished":False,"session_id":session.session_id,"scene":scene["name"],"scene_number":session.scene_index+1,"scene_count":len(SCENES),"left":scene["left"],"right":scene["right"],"difference_count":len(scene["differences"]),"found":sorted(session.found)}

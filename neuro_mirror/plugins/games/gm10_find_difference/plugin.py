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
    scenes: list[dict[str, Any]]
    stimulus_set: str
    difficulty_level: int
    scene_index: int = 0
    found: set[int] = field(default_factory=set)
    shown_ms: float = field(default_factory=lambda: time.time()*1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm10FindDifferencePlugin(BrowserGamePlugin):
    plugin_name="gm10_find_difference"; game_code="GM-10"; start_handler="_start"; answer_handler="_answer"
    def __init__(self,bus): super().__init__(bus); self._sessions={}
    def start_game(self,payload):
        return self._start(stimulus_set=str(payload.get("stimulus_set") or ""),difficulty_level=payload.get("difficulty_level"))
    def _start(self,*,stimulus_set="",difficulty_level=None):
        scenes_by_name={str(scene["name"]).casefold():scene for scene in SCENES}
        available=tuple(name for name in self.definition.stimulus_sets if name.casefold() in scenes_by_name) or tuple(scenes_by_name)
        requested=next((name for name in available if name.casefold()==stimulus_set.casefold()),available[0])
        if difficulty_level in (None, ""):
            selected=requested
            level=(4,6,9).index(len(scenes_by_name[selected.casefold()]["differences"]))+1
        else:
            try:level=min(3,max(1,int(difficulty_level)))
            except (TypeError,ValueError):level=1
            selected=available[level-1]
        session=DifferenceSession(uuid.uuid4().hex,[scenes_by_name[selected.casefold()]],selected,level);self._sessions[session.session_id]=session;return self._payload(session)
    def _answer(self,payload):
        session=self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:return {"ok":False,"message":"Игровая сессия не найдена."}
        x,y=float(payload.get("x",-1)),float(payload.get("y",-1));scene=session.scenes[session.scene_index]
        hit=next((i for i,(dx,dy) in enumerate(scene["differences"]) if i not in session.found and math.dist((x,y),(dx,dy))<=scene["radius"]),None)
        correct=hit is not None
        if correct:session.found.add(hit)
        session.round_events.append({"scene":scene["name"],"clicks":[x,y],"difference_id":hit,"correct":correct,"reaction_ms":max(0,time.time()*1000-session.shown_ms)})
        scene_complete=len(session.found)==len(scene["differences"])
        if scene_complete:
            session.scene_index+=1;session.found=set();session.shown_ms=time.time()*1000
            if session.scene_index==len(session.scenes):
                events=list(session.round_events);self._sessions.pop(session.session_id,None)
                return {"ok":True,"finished":True,"correct":True,"events":events,"metrics":score_gm10(events,sum(len(s["differences"]) for s in session.scenes))}
        result=self._payload(session);result.update({"correct":correct,"hit":hit,"scene_complete":scene_complete});return result
    def _payload(self,session):
        scene=session.scenes[session.scene_index]
        return {"ok":True,"finished":False,"session_id":session.session_id,"stimulus_set":session.stimulus_set,"difficulty_level":session.difficulty_level,"difficulty_parameters":{"differences":len(scene["differences"])},"scene":scene["name"],"scene_number":session.scene_index+1,"scene_count":len(session.scenes),"left":scene["left"],"right":scene["right"],"difference_count":len(scene["differences"]),"found":sorted(session.found)}

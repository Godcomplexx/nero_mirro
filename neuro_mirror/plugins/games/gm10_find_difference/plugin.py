from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import END_TIMEOUT, BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import time_limit_ms, time_limit_visible
from neuro_mirror.plugins.games.gm10_find_difference.stimuli import SCENES_BY_LEVEL, STIMULUS_SET_VERSION
from neuro_mirror.plugins.games.task_clock import TaskClock
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
    # Лимит времени задания (методика, раздел 7: «за фиксированное время»)
    clock: TaskClock | None = None


class Gm10FindDifferencePlugin(BrowserGamePlugin):
    plugin_name="gm10_find_difference"; game_code="GM-10"; start_handler="_start"; answer_handler="_answer"
    def __init__(self,bus): super().__init__(bus); self._sessions={}
    def start_game(self,payload):
        return self._start(stimulus_set=str(payload.get("stimulus_set") or ""),difficulty_level=payload.get("difficulty_level"))
    def _start(self,*,stimulus_set="",difficulty_level=None):
        try:level=min(3,max(1,int(difficulty_level or 1)))
        except (TypeError,ValueError):level=1
        available=tuple(self.definition.stimulus_sets)
        selected=next((name for name in available if name.casefold()==stimulus_set.casefold()),available[level-1])
        scenes=list(SCENES_BY_LEVEL[level])
        session=DifferenceSession(uuid.uuid4().hex,scenes,selected,level)
        limit=time_limit_ms(self.game_code,level)
        if limit:session.clock=TaskClock(limit)
        self._sessions[session.session_id]=session;return self._payload(session)
    def _answer(self,payload):
        session=self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:return {"ok":False,"message":"Игровая сессия не найдена."}
        x,y=float(payload.get("x",-1)),float(payload.get("y",-1));scene=session.scenes[session.scene_index]
        hit=next((i for i,(dx,dy) in enumerate(scene["differences"]) if i not in session.found and math.dist((x,y),(dx,dy))<=scene["radius"]),None)
        correct=hit is not None
        if correct:session.found.add(hit)
        session.round_events.append({"scene":scene["name"],"scene_number":session.scene_index+1,"clicks":[x,y],"difference_id":hit,"correct":correct,"reaction_ms":max(0,time.time()*1000-session.shown_ms)})
        scene_complete=len(session.found)==len(scene["differences"])
        if scene_complete:
            session.scene_index+=1;session.found=set();session.shown_ms=time.time()*1000
            if session.clock is not None:session.clock.end_trial()
            if session.scene_index==len(session.scenes):
                events=list(session.round_events);self._sessions.pop(session.session_id,None)
                return {"ok":True,"finished":True,"correct":True,"events":events,"time_limit_ms":session.clock.limit_ms if session.clock else None,"metrics":score_gm10(events,sum(len(s["differences"]) for s in session.scenes),finished=True)}
        result=self._payload(session);result.update({"correct":correct,"hit":hit,"scene_complete":scene_complete});return result
    def _resume(self,session,paused_ms):
        """Сцена, на которой нажата пауза, начинается заново: найденные в ней
        отличия прерванной пробы не оцениваются (4.5, п. 5)."""
        number=session.scene_index+1
        session.round_events=[event for event in session.round_events if event.get("scene_number")!=number]
        session.found=set();session.shown_ms=time.time()*1000
        if session.clock is not None:session.clock.restart_trial()
        return self._payload(session)
    def _trial_number(self,session):
        return session.scene_index+1
    def _timeout(self,session):
        if session.clock is None or not session.clock.expired():
            return {"ok":False,"message":"Время задания ещё не вышло."}
        events=list(session.round_events);self._sessions.pop(session.session_id,None)
        return {"ok":True,"finished":True,"end_reason":END_TIMEOUT,"events":events,"time_limit_ms":session.clock.limit_ms,
                "metrics":score_gm10(events,sum(len(s["differences"]) for s in session.scenes),finished=False)}
    def _payload(self,session):
        scene=session.scenes[session.scene_index];clock=session.clock
        return {"time_limit_ms":clock.limit_ms if clock else None,"time_left_ms":clock.left_ms() if clock else None,
                "time_visible":time_limit_visible(self.game_code) if clock else False,"ok":True,"finished":False,"session_id":session.session_id,"stimulus_set":session.stimulus_set,"stimulus_set_version":STIMULUS_SET_VERSION,"difficulty_level":session.difficulty_level,"difficulty_parameters":{"differences":len(scene["differences"])},"scene":scene["name"],"scene_number":session.scene_index+1,"scene_count":len(session.scenes),"left":scene["left"],"right":scene["right"],"difference_count":len(scene["differences"]),"found":sorted(session.found)}

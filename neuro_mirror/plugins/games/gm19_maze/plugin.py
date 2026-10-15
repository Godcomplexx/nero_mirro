from __future__ import annotations
import collections, secrets, time, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm19_maze.stimuli import DIRS
from neuro_mirror.screening.gm19_scoring import score_gm19_mazes
@dataclass(slots=True)
class MazeSession:
    session_id:str; mazes:list[dict[str,Any]]; difficulty_level:int; difficulty_parameters:dict[str,Any]
    index:int=0; shown_at_ms:float=0.0; results:list[dict[str,Any]]=field(default_factory=list)
class Gm19MazePlugin(BrowserGamePlugin):
    plugin_name="gm19_maze"
    game_code="GM-19"
    def __init__(self,bus):super().__init__(bus);self._sessions={};self._random=secrets.SystemRandom()
    def _generate_once(self,size,rng):
        walls=[[{"n":True,"e":True,"s":True,"w":True} for _ in range(size)] for _ in range(size)]
        visited={(0,0)};stack=[(0,0)]
        while stack:
            x,y=stack[-1]; options=[]
            for dx,dy,d,opp in DIRS:
                nx,ny=x+dx,y+dy
                if 0<=nx<size and 0<=ny<size and (nx,ny) not in visited:options.append((nx,ny,d,opp))
            if not options:stack.pop();continue
            nx,ny,d,opp=rng.choice(options);walls[y][x][d]=False;walls[ny][nx][opp]=False;visited.add((nx,ny));stack.append((nx,ny))
        return {"size":size,"walls":walls,"start":[0,0],"finish":[size-1,size-1],"shortest_steps":self._shortest(walls,size)}
    def _generate(self,size,minimum_shortest_steps,rng):
        best=None
        for _ in range(100):
            maze=self._generate_once(size,rng)
            if best is None or maze["shortest_steps"]>best["shortest_steps"]:best=maze
            if maze["shortest_steps"]>=minimum_shortest_steps:return maze
        return best
    def _shortest(self,walls,size):
        queue=collections.deque([((0,0),0)]);seen={(0,0)}
        while queue:
            (x,y),dist=queue.popleft()
            if (x,y)==(size-1,size-1):return dist
            for dx,dy,d,_ in DIRS:
                nx,ny=x+dx,y+dy
                if not walls[y][x][d] and (nx,ny) not in seen:seen.add((nx,ny));queue.append(((nx,ny),dist+1))
        return 0
    def start_game(self,payload):
        return self._start(difficulty_level=payload.get("difficulty_level"),rng=self._session_random(payload))
    def _start(self,*,difficulty_level=None,rng=None):
        rng=rng or self._random
        config=level_config(self.game_code)
        try:level=int(difficulty_level or config["default_level"])
        except (TypeError,ValueError):level=int(config["default_level"])
        available={int(item["level"]):item for item in config["levels"]}
        if level not in available:level=int(config["default_level"])
        parameters=dict(available[level]["parameters"]);size=int(parameters["size"]);count=int(parameters["mazes"]);minimum=int(parameters["minimum_shortest_steps"])
        s=MazeSession(uuid.uuid4().hex,[self._generate(size,minimum,rng) for _ in range(count)],level,parameters);self._sessions[s.session_id]=s;return self._payload(s)
    def _resume(self,s,paused_ms):
        """Прерванный лабиринт проходится заново (4.5, п. 5)."""
        return self._payload(s)
    def _trial_number(self,s):
        return s.index+1
    def _payload(self,s):
        s.shown_at_ms=time.time()*1000;m=s.mazes[s.index]
        return {"ok":True,"finished":False,"session_id":s.session_id,"maze":s.index+1,"maze_count":len(s.mazes),
                "difficulty_level":s.difficulty_level,"difficulty_parameters":dict(s.difficulty_parameters),
                "size":m["size"],"walls":m["walls"],"start":m["start"],"finish":m["finish"]}
    @staticmethod
    def _valid_path(maze,path):
        if not path or path[0]!=maze["start"] or path[-1]!=maze["finish"]:return False
        for left,right in zip(path,path[1:]):
            x,y=left;nx,ny=right;match=next((d for dx,dy,d,_ in DIRS if (x+dx,y+dy)==(nx,ny)),None)
            if match is None or maze["walls"][y][x][match]:return False
        return True
    def _answer(self,payload):
        s=self._sessions.get(str(payload.get("session_id") or ""))
        if s is None:return {"ok":False,"message":"Игровая сессия не найдена."}
        raw=payload.get("path");path=[]
        if isinstance(raw,list):
            for cell in raw:
                if isinstance(cell,list) and len(cell)==2:
                    try:path.append([int(cell[0]),int(cell[1])])
                    except (TypeError,ValueError):pass
        maze=s.mazes[s.index];valid=self._valid_path(maze,path)
        if not valid:return {"ok":False,"message":"Маршрут не достигает финиша по проходам лабиринта."}
        s.results.append({"maze":s.index+1,"path":path,"shortest_steps":maze["shortest_steps"],"valid_path":True,
                          "boundary_errors":max(0,int(payload.get("boundary_errors") or 0)),"planning_ms":max(0,float(payload.get("planning_ms") or 0)),
                          "execution_ms":max(0,float(payload.get("execution_ms") or 0)),"server_duration_ms":max(0,time.time()*1000-s.shown_at_ms)})
        s.index+=1
        if s.index==len(s.mazes):
            self._sessions.pop(s.session_id,None);return {"ok":True,"finished":True,"metrics":score_gm19_mazes(s.results, expected_mazes=len(s.mazes)),"events":s.results}
        return self._payload(s)

"""Scenario for a catalogued browser game (Math Quiz)."""
from __future__ import annotations
import time
import uuid
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.trial_journal import TrialJournal
from .stimuli import STIMULI

class MathQuizGamePlugin(BrowserGamePlugin):
    plugin_name = "math_quiz"
    game_code = "GM-MATH01"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, dict[str, Any]] = {}

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Create the session, choose a stimulus set and start active timing.
        session_id = str(uuid.uuid4())
        journal = TrialJournal(game_id=self.game_code, session_id=session_id)
        
        self._sessions[session_id] = {
            "journal": journal,
            "stimuli": list(STIMULI),
            "current_index": 0,
            "score": 0,
            "start_time": time.time()
        }
        
        current_stimulus = self._sessions[session_id]["stimuli"][0]
        return {
            "session_id": session_id,
            "status": "started",
            "current_question": current_stimulus["question"],
            "question_number": 1,
            "total_questions": len(STIMULI)
        }

    def answer_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Record the first answer before feedback. Return a checkpoint after
        # every assessed unit and a report-compatible result on completion.
        session_id = payload.get("session_id")
        if session_id not in self._sessions:
            return {"status": "error", "message": "Invalid session"}

        session = self._sessions[session_id]
        journal: TrialJournal = session["journal"]
        current_index = session["current_index"]
        current_stimulus = session["stimuli"][current_index]
        
        user_answer = payload.get("answer")
        # Приводим к строке для безопасного сравнения
        is_correct = str(user_answer).strip() == str(current_stimulus["answer"])
        
        if is_correct:
            session["score"] += 1
        
        # Записываем попытку в журнал
        journal.record_trial(
            stimulus=current_stimulus["question"],
            response=user_answer,
            correct=is_correct
        )
        
        session["current_index"] += 1
        
        # Проверяем, закончилась ли игра
        if session["current_index"] >= len(session["stimuli"]):
            end_time = time.time()
            duration = end_time - session["start_time"]
            del self._sessions[session_id] # Очищаем сессию
            
            return {
                "status": "completed",
                "score": session["score"],
                "total_questions": len(STIMULI),
                "duration_seconds": round(duration, 2),
                "feedback": "Игра завершена!"
            }
        
        # Возвращаем чекпоинт и следующий вопрос
        next_stimulus = session["stimuli"][session["current_index"]]
        return {
            "status": "checkpoint",
            "feedback": "Верно!" if is_correct else f"Неверно. Правильный ответ: {current_stimulus['answer']}",
            "current_question": next_stimulus["question"],
            "question_number": session["current_index"] + 1,
            "total_questions": len(STIMULI)
        }

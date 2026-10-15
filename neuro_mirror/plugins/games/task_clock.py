"""Лимит времени задания («Методика подбора и оценки тренировочного курса» v2).

Задание кончается одним из способов: выполнено, исчерпаны попытки или
исчерпан лимит времени (4.5, п. 1). Лимит считается по активному времени:
пауза в него не входит (4.5, п. 4). После паузы прерванная проба
проходится заново (4.5, п. 5), поэтому её время отбрасывается, а время
законченных проб остаётся.

Часы ведёт ядро; интерфейс только узнаёт из ответа, сколько осталось
(``time_left_ms``), и, когда время вышло, сообщает об этом игре. Ядро
проверяет это по своим часам: задание не кончится раньше лимита из-за
поторопившегося интерфейса.
"""
from __future__ import annotations

import time

# Запас на задержку запроса: интерфейс может сообщить о конце времени чуть
# раньше, чем истечёт лимит по часам ядра.
TIMEOUT_TOLERANCE_MS = 1500.0


def _now_ms() -> float:
    return time.time() * 1000


class TaskClock:
    def __init__(self, limit_ms: float) -> None:
        self.limit_ms = float(limit_ms)
        # Время законченных проб
        self.finished_trials_ms = 0.0
        self.trial_started_ms = _now_ms()

    def end_trial(self) -> None:
        """Проба закончена: её время входит в задание, отсчёт новой пробы."""
        now = _now_ms()
        self.finished_trials_ms += max(0.0, now - self.trial_started_ms)
        self.trial_started_ms = now

    def restart_trial(self) -> None:
        """Прерванная проба начинается заново: её прошедшее время не считается."""
        self.trial_started_ms = _now_ms()

    def elapsed_ms(self) -> float:
        return self.finished_trials_ms + max(0.0, _now_ms() - self.trial_started_ms)

    def left_ms(self) -> int:
        return int(max(0.0, self.limit_ms - self.elapsed_ms()))

    def expired(self) -> bool:
        return self.elapsed_ms() + TIMEOUT_TOLERANCE_MS >= self.limit_ms

"""Версии приложения и сценариев (требование ТЗ п.6.3.7, 6.8).

APP_VERSION — версия программной части в целом.
SCENARIO_VERSIONS — версии сценариев тестов: меняйте при любом изменении
заданий, формулировок или правил подсчёта, чтобы результаты в хранилище
можно было корректно сравнивать между собой.
"""
from __future__ import annotations

APP_VERSION = "0.5.0"

SCENARIO_VERSIONS: dict[str, str] = {
    "screening": "1.0.0",  # базовый скрининг: видео-анализ + HADS
    "hads": "1.0.0",       # тест на тревожность (HADS), 14 вопросов
    "moca": "1.0.0",       # аудио-MoCA, 11 заданий
}


def version_summary() -> dict[str, str]:
    return {"app": APP_VERSION, **SCENARIO_VERSIONS}

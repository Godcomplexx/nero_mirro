"""Версии приложения и сценариев (требование ТЗ п.6.3.7, 6.8).

APP_VERSION — версия программной части в целом.
SCENARIO_VERSIONS — версии сценариев тестов: меняйте при любом изменении
заданий, формулировок или правил подсчёта, чтобы результаты в хранилище
можно было корректно сравнивать между собой.
"""
from __future__ import annotations

APP_VERSION = "0.6.0"

SCENARIO_VERSIONS: dict[str, str] = {
    "screening": "1.0.0",  # базовый скрининг: видео-анализ + HADS
    "hads": "1.0.0",       # тест на тревожность (HADS), 14 вопросов
    "moca": "1.1.0",       # аудио-MoCA, 11 заданий
}

INTERFACE_VERSION = "1.1.0"

ALGORITHM_VERSIONS: dict[str, str] = {
    "session_conditions": "1.0.0",
    "rppg_pipeline": "1.0.0",
    "hads_scoring": "1.0.0",
    "voice_moca_scoring": "1.1.0",
}

INTERPRETATION_RULES_VERSION = "1.0.0"


def version_summary() -> dict[str, str]:
    return {"app": APP_VERSION, **SCENARIO_VERSIONS}


def session_version_manifest(
    scenario: str,
    *,
    stt_model: str = "",
    emotion_model: str = "",
) -> dict[str, object]:
    return {
        "app": APP_VERSION,
        "interface": INTERFACE_VERSION,
        "scenario": SCENARIO_VERSIONS.get(scenario, ""),
        "algorithms": dict(ALGORITHM_VERSIONS),
        "models": {
            "stt": stt_model,
            "emotion": emotion_model,
        },
        "interpretation_rules": INTERPRETATION_RULES_VERSION,
    }

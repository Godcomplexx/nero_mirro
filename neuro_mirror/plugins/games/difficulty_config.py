"""Load and validate the JSON difficulty configuration for games.

Statuses of a game's levels (game_levels.json):

* ``configured`` — values from the approved «Матрица игр v5»;
* ``draft`` — preliminary values: the matrix leaves them empty, they are used
  for the pilot and may still change. The game runs on them; the course does
  not change the level of such a game (screening/difficulty_policy.py);
* ``not_configured`` — no levels at all.

Each game also says where its values come from (``source``) and may carry a
``note``. The table of all values is docs/game-levels.md.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from neuro_mirror.plugins.games.contracts import DifficultyLevel, normalise_game_code


CONFIG_PATH = Path(__file__).with_name("game_levels.json")
STATUS_CONFIGURED = "configured"
STATUS_DRAFT = "draft"
STATUS_NOT_CONFIGURED = "not_configured"
VALID_STATUSES = {STATUS_CONFIGURED, STATUS_DRAFT, STATUS_NOT_CONFIGURED}


@lru_cache(maxsize=1)
def load_game_level_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        document = json.load(stream)
    if document.get("schema_version") != 1:
        raise RuntimeError("game_levels.json: неподдерживаемая версия схемы")
    games = document.get("games")
    if not isinstance(games, dict):
        raise RuntimeError("game_levels.json: поле games должно быть объектом")
    for code, config in games.items():
        if normalise_game_code(code) != code or not isinstance(config, dict):
            raise RuntimeError(f"game_levels.json: некорректная запись {code!r}")
        status = config.get("status")
        levels = config.get("levels")
        if status not in VALID_STATUSES or not isinstance(levels, list):
            raise RuntimeError(f"game_levels.json: некорректная конфигурация {code}")
        numbers = [item.get("level") for item in levels if isinstance(item, dict)]
        if len(numbers) != len(levels) or numbers != list(range(1, len(levels) + 1)):
            raise RuntimeError(f"game_levels.json: уровни {code} должны идти подряд с 1")
        if status in (STATUS_CONFIGURED, STATUS_DRAFT) and not levels:
            raise RuntimeError(f"game_levels.json: для {code} не заданы уровни")
        if not str(config.get("source") or "").strip():
            raise RuntimeError(f"game_levels.json: для {code} не указан источник значений")
        if status == STATUS_NOT_CONFIGURED and levels:
            raise RuntimeError(f"game_levels.json: {code} помечена как ненастроенная")
        if int(config.get("default_level", 1)) not in (numbers or [1]):
            raise RuntimeError(f"game_levels.json: неверный default_level для {code}")
    return document


def public_game_level_config() -> dict[str, Any]:
    """Return an isolated JSON-compatible configuration for API clients."""
    return deepcopy(load_game_level_config())


def level_config(game_code: str) -> dict[str, Any]:
    code = normalise_game_code(game_code)
    try:
        return deepcopy(load_game_level_config()["games"][code])
    except KeyError as exc:
        raise KeyError(f"Для игры {code} нет конфигурации сложности") from exc


def difficulty_levels(game_code: str) -> tuple[DifficultyLevel, ...]:
    config = level_config(game_code)
    return tuple(
        DifficultyLevel(int(item["level"]), dict(item.get("parameters") or {}))
        for item in config["levels"]
    )


def level_status(game_code: str) -> str:
    """Утверждены ли уровни игры: configured, draft или not_configured."""
    return str(level_config(game_code).get("status") or STATUS_NOT_CONFIGURED)

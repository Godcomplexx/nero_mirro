"""Automatic discovery and validation of implemented game plugins."""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import re
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator, Type

from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.plugins import games
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.catalog import GAME_CATALOG, get_game_definition
from neuro_mirror.plugins.games.contracts import GameDefinition


GAME_CODE_PATTERN = re.compile(r"^GM-[A-Z0-9][A-Z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class GameRegistration:
    definition: GameDefinition
    plugin_class: Type[Plugin]
    package_name: str


@lru_cache(maxsize=1)
def discover_game_registrations() -> tuple[GameRegistration, ...]:
    registrations: list[GameRegistration] = []
    seen_codes: set[str] = set()
    prefix = f"{games.__name__}."
    for module_info in pkgutil.iter_modules(games.__path__, prefix):
        if not module_info.ispkg or module_info.name.rsplit(".", 1)[-1].startswith("_"):
            continue
        package_leaf = module_info.name.rsplit(".", 1)[-1]
        plugin_module = importlib.import_module(f"{module_info.name}.plugin")
        classes = [
            candidate
            for _, candidate in inspect.getmembers(plugin_module, inspect.isclass)
            if issubclass(candidate, Plugin)
            and candidate is not Plugin
            and candidate.__module__ == plugin_module.__name__
        ]
        if len(classes) != 1:
            raise RuntimeError(
                f"{module_info.name}.plugin должен содержать ровно один класс Plugin; найдено {len(classes)}"
            )
        game_code = str(getattr(classes[0], "game_code", "") or "")
        if not game_code:
            raise RuntimeError(
                f"{module_info.name}.plugin должен задать game_code из каталога"
            )
        game_code = game_code.strip().upper()
        if not GAME_CODE_PATTERN.fullmatch(game_code):
            raise RuntimeError(
                f"Игра {package_leaf!r} использует недопустимый game_code {game_code!r}; "
                "ожидается формат GM-..."
            )
        try:
            definition = get_game_definition(game_code)
        except KeyError:
            definition = getattr(classes[0], "game_definition", None)
            if not isinstance(definition, GameDefinition):
                raise RuntimeError(
                    f"Новый код {game_code!r} отсутствует в исходном каталоге; "
                    f"класс {classes[0].__name__} должен задать game_definition"
                )
            if definition.code.strip().upper() != game_code:
                raise RuntimeError(
                    f"game_code {game_code!r} не совпадает с game_definition.code {definition.code!r}"
                )
        if issubclass(classes[0], BrowserGamePlugin):
            package_spec = importlib.util.find_spec(module_info.name)
            package_path = (
                Path(next(iter(package_spec.submodule_search_locations)))
                if package_spec and package_spec.submodule_search_locations
                else None
            )
            if package_path is None or not (package_path / "web.js").is_file():
                raise RuntimeError(f"{module_info.name} использует новый шаблон, но не содержит web.js")
        if definition.code in seen_codes:
            raise RuntimeError(f"Повторная реализация игры {definition.code}")
        seen_codes.add(definition.code)
        registrations.append(GameRegistration(definition, classes[0], module_info.name))
    return tuple(sorted(registrations, key=lambda item: item.definition.code))


def iter_game_plugins(bus) -> Iterator[Plugin]:
    for registration in discover_game_registrations():
        yield registration.plugin_class(bus)


def implemented_game_codes() -> frozenset[str]:
    return frozenset(item.definition.code for item in discover_game_registrations())


def all_game_definitions() -> tuple[GameDefinition, ...]:
    """Return the spreadsheet catalog plus definitions supplied by new plugins."""
    definitions = {item.code: item for item in GAME_CATALOG}
    for registration in discover_game_registrations():
        definitions[registration.definition.code] = registration.definition
    return tuple(sorted(definitions.values(), key=lambda item: item.code))


def get_available_game_definition(code_or_slug: str) -> GameDefinition:
    try:
        return get_game_definition(code_or_slug)
    except KeyError:
        value = code_or_slug.strip().upper().replace("_", "-")
        if value.startswith("GM") and not value.startswith("GM-"):
            value = f"GM-{value[2:]}"
        for definition in all_game_definitions():
            if definition.code == value or definition.slug == code_or_slug:
                return definition
        raise KeyError(f"Неизвестный код игры: {code_or_slug}")


def game_asset_path(code: str, filename: str) -> Path | None:
    if filename not in {"web.js", "styles.css"}:
        raise ValueError("Недопустимое имя игрового ресурса")
    registration = next(
        (item for item in discover_game_registrations() if item.definition.code == code),
        None,
    )
    if registration is None:
        return None
    spec = importlib.util.find_spec(registration.package_name)
    if spec is None or not spec.submodule_search_locations:
        return None
    path = Path(next(iter(spec.submodule_search_locations))) / filename
    return path if path.is_file() else None

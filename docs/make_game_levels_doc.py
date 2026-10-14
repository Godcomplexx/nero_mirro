"""Собрать docs/game-levels.md из neuro_mirror/plugins/games/game_levels.json.

Таблица генерируется, а не пишется руками: так документ не расходится с
файлом, по которому работают игры. После правки game_levels.json запустите:

    python docs/make_game_levels_doc.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "neuro_mirror" / "plugins" / "games" / "game_levels.json"
TARGET = ROOT / "docs" / "game-levels.md"

# Подписи параметров. Новый параметр без подписи выводится своим ключом.
LABELS = {
    "block_correct_counts": "верных шагов в блоках",
    "block_duration_ms": "длительность блока, мс",
    "category_count": "категорий",
    "category_switches": "смен категории",
    "choice_words": "слов на выбор",
    "choices": "вариантов выбора",
    "cycles": "циклов",
    "difference_range": "отличий в сцене",
    "display_ms": "показ стимула, мс",
    "elements": "элементов башни",
    "grid": "сетка",
    "grid_size": "размер сетки",
    "items": "изображений",
    "letter_range": "букв в слове",
    "letters": "буквы",
    "max_recording_ms": "предел записи, мс",
    "mazes": "лабиринтов",
    "minimum_shortest_steps": "кратчайший путь не короче, шагов",
    "missing_items": "исчезнувших предметов",
    "movement_ms": "движение, мс",
    "object_count": "объектов",
    "operation_switches": "смен операции",
    "option_count": "вариантов ответа",
    "pair_counts": "пар на доске",
    "pattern_mode": "тип закономерности",
    "pieces": "фрагментов",
    "puzzles": "пазлов",
    "recording_ms": "запись ответа, мс",
    "rule_block_size": "проб до смены правила",
    "rule_switches": "смен правила",
    "scene_count": "сцен",
    "size": "размер лабиринта",
    "study_ms": "время запоминания, мс",
    "style_count": "стилей",
    "switch_every": "смена каждые N проб",
    "target_present_range": "проб с целью",
    "target_range": "подсвеченных клеток",
    "target_words": "слов для запоминания",
    "tracked_objects": "отслеживаемых объектов",
    "trial_slot_ms": "окно пробы, мс",
    "trials": "проб",
}

STATUS = {
    "configured": "утверждено (матрица)",
    "draft": "предварительно",
    "not_configured": "не задано",
}


def value(key: str, raw: object) -> str:
    # Диапазон — только у параметров «…_range»; остальные списки — перечень
    # (например, две доски по 5 пар — «5, 5», а не «5–5»)
    if isinstance(raw, list):
        if key.endswith("_range") and len(raw) == 2:
            return str(raw[0]) if raw[0] == raw[1] else f"{raw[0]}–{raw[1]}"
        return ", ".join(str(item) for item in raw)
    return str(raw)


def level_text(parameters: dict) -> str:
    return "; ".join(f"{LABELS.get(key, key)}: {value(key, raw)}" for key, raw in parameters.items())


def main() -> None:
    games = json.loads(SOURCE.read_text(encoding="utf-8"))["games"]
    lines = [
        "# Уровни сложности игр",
        "",
        "Документ собран из `neuro_mirror/plugins/games/game_levels.json` скриптом",
        "`docs/make_game_levels_doc.py`. Руками его не правят: после изменения JSON",
        "скрипт запускают заново.",
        "",
        "## Статусы",
        "",
        "- **утверждено (матрица)** — значения из «Матрицы игр v5» от 08.09.2026;",
        "- **предварительно** (`draft`) — в матрице значений нет. Игра работает на",
        "  этих уровнях во время апробации, значения могут измениться.",
        "",
        "Меняет ли курс уровень игры по правильности прохождений, задаёт",
        "`neuro_mirror/screening/difficulty_policy.py` (таблица `SUCCESS_COUNTS`), а не",
        "этот файл.",
        "",
        "## Как поменять одно значение",
        "",
        "1. Открыть `neuro_mirror/plugins/games/game_levels.json` и найти игру по коду.",
        "2. Поменять число в `parameters` нужного уровня. Ключи параметров не",
        "   переименовывать — по ним значение читает игра.",
        "3. Когда значения игры утверждены, поменять `status` с `draft` на",
        "   `configured` и записать в `source`, чем они утверждены.",
        "4. Запустить `python docs/make_game_levels_doc.py` и тесты.",
        "",
        "## Таблица",
        "",
        "| Код | Статус | Уровень 1 | Уровень 2 | Уровень 3 | Примечание |",
        "|---|---|---|---|---|---|",
    ]
    for code, game in games.items():
        levels = {item["level"]: level_text(item.get("parameters") or {}) for item in game["levels"]}
        lines.append(
            f"| {code} | {STATUS.get(game['status'], game['status'])} | "
            f"{levels.get(1, '—')} | {levels.get(2, '—')} | {levels.get(3, '—')} | "
            f"{game.get('note', '')} |"
        )
    lines.append("")
    TARGET.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
import os
from pathlib import Path

_log = logging.getLogger("neuro_mirror.assistant_rules")

DEFAULT_ASSISTANT_RULES_PATH = Path(__file__).with_name("assistant_rules.md")

_FALLBACK_ASSISTANT_RULES = """\
# Правила поведения ассистента Нейро-зеркало

- Ты умный помощник приложения "Нейро-зеркало".
- Отвечай спокойно, кратко и на языке пользователя; по умолчанию используй русский.
- Распознавай команды start_screening, analyze_appearance и camera_vision_query отдельно от обычных вопросов.
- Если это обычный вопрос, отвечай как помощник и не показывай список команд приложения.
- Для актуальных фактов используй проверенные данные; не выдумывай текущие события.
- Если речь распознана плохо и смысл неясен, попроси повторить или уточнить.
- В медицинских и психологических темах не ставь диагнозы и советуй специалиста при рисках.
"""

# --- mtime-based hot-reload cache ---
_cached_rules: str = ""
_cached_mtime: float = 0.0
_cached_path: str = ""

_REQUIRED_SECTIONS = (
    "Роль",
    "Тон и формат",
    "Команды приложения",
    "Медицина и психология",
    "Vision и внешность",
)


def load_assistant_rules(path: str = "") -> str:
    """Load assistant rules from file with mtime-based caching.

    On subsequent calls with the same *path*, the file is re-read only when its
    modification time changes.  This makes hot-reload essentially free and
    allows editing the rules file without restarting the application.
    """
    global _cached_rules, _cached_mtime, _cached_path  # noqa: PLW0603

    rules_path = Path(path).expanduser() if path.strip() else DEFAULT_ASSISTANT_RULES_PATH
    resolved = str(rules_path)

    try:
        current_mtime = os.path.getmtime(resolved)
    except OSError:
        return _FALLBACK_ASSISTANT_RULES.strip()

    # Return cache if path and mtime haven't changed
    if resolved == _cached_path and current_mtime == _cached_mtime and _cached_rules:
        return _cached_rules

    try:
        text = rules_path.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_ASSISTANT_RULES.strip()

    if not text:
        return _FALLBACK_ASSISTANT_RULES.strip()

    # Validate and warn about missing sections (non-blocking)
    warnings = validate_assistant_rules(text)
    for warning in warnings:
        _log.warning("assistant_rules: %s", warning)

    # Update cache
    _cached_rules = text
    _cached_mtime = current_mtime
    _cached_path = resolved

    return text


def validate_assistant_rules(text: str) -> list[str]:
    """Check that *text* contains all expected section headers.

    Returns a list of human-readable warning strings (empty if everything is
    present).  This never raises — it is advisory only.
    """
    warnings: list[str] = []
    lowered = text.lower()
    for section in _REQUIRED_SECTIONS:
        # Match "## Роль" / "## роль" etc.
        marker = f"## {section.lower()}"
        if marker not in lowered:
            warnings.append(f"Отсутствует обязательная секция «## {section}»")
    return warnings


def invalidate_rules_cache() -> None:
    """Force the next ``load_assistant_rules`` call to re-read the file."""
    global _cached_rules, _cached_mtime, _cached_path  # noqa: PLW0603
    _cached_rules = ""
    _cached_mtime = 0.0
    _cached_path = ""

from __future__ import annotations

from pathlib import Path


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


def load_assistant_rules(path: str = "") -> str:
    rules_path = Path(path).expanduser() if path.strip() else DEFAULT_ASSISTANT_RULES_PATH
    try:
        text = rules_path.read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_ASSISTANT_RULES.strip()
    return text or _FALLBACK_ASSISTANT_RULES.strip()

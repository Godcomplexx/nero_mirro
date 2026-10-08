"""Журнал обращений к результатам.

Отдельный от технического журнала и от журнала сессий. Отвечает на вопрос
«кто и когда открывал результаты», который задают при регистрации
медицинского изделия: сам факт просмотра и выгрузки должен быть
прослеживаемым, даже когда содержание результата не менялось.

Записи дописываются по одной строке и не переписываются: журнал доступа,
который можно исправить задним числом, теряет смысл. Содержимое самих
результатов сюда не попадает — только кто, когда и к чему обратился.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("runtime/deidentified/access.jsonl")

# Виды обращений, которые фиксируются.
VIEW_RESULTS = "results_view"
EXPORT_RESULTS = "results_export"


class AccessJournal:
    """Дописывает записи об обращениях к результатам."""

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(
        self,
        *,
        action: str,
        user_id: str,
        session_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Записать обращение.

        Сбой записи не должен мешать человеку смотреть свои результаты,
        поэтому ошибка только отмечается в техническом журнале.
        """
        entry = {
            "at": datetime.now(UTC).isoformat(),
            "action": action,
            "user_id": user_id,
            "session_id": session_id,
            # Учётная запись операционной системы: она отвечает на вопрос,
            # с какого рабочего места выполнено обращение.
            "account": os.getenv("USERNAME") or "",
        }
        if details:
            entry["details"] = details
        line = json.dumps(entry, ensure_ascii=False)
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError as exc:
            logger.warning("не удалось записать обращение к результатам: %s", exc)

"""Настройка технического журнала.

Журнал служит для разбора неисправностей, а не для хранения результатов, и
потому подчиняется трём правилам.

Объём ограничен: файл закрывается по достижении предельного размера, число
файлов фиксировано, старое удаляется само. Без этого журнал растёт до тех пор,
пока не кончится место на диске.

Персональные данные в него не попадают. Ответы пациента, расшифровки речи и
имена — это сведения о состоянии здоровья, и запись их в файл, который потом
передают в поддержку, недопустима. Основное средство — не писать их в местах
вызова; фильтр здесь работает как страховка на случай недосмотра.

Доступ ограничен: каталог журналов открыт учётной записи, от имени которой
работает программа, и администраторам. Остальным чтение закрыто.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_LOG_DIR = Path("runtime/logs")
LOG_FILE_NAME = "neuro_mirror.log"

# Предельный размер одного файла и их количество. Десять мегабайт — это около
# сотни тысяч строк: для разбора одного сеанса работы хватает с запасом, а пять
# файлов удерживают историю последних дней.
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

LEVELS: dict[str, int] = {
    "errors": logging.ERROR,
    "normal": logging.INFO,
    "debug": logging.DEBUG,
    # Привычные обозначения принимаются наравне с описательными.
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
}

REDACTED = "<скрыто>"

# Слова, после которых в записи может оказаться содержание ответа.
_SENSITIVE_WORDS = (
    r"транскрипц\w*",
    r"расшифровк\w*",
    r"transcript\w*",
    r"ответ\w*",
    r"answer\w*",
    r"реплик\w*",
    r"высказыван\w*",
)
_WORDS = "|".join(_SENSITIVE_WORDS)

# Значение в кавычках рядом с таким словом. Небольшой разрыв до кавычки
# допускается: так покрываются и «ответ: "..."», и «не распознан ответ из '...'».
_QUOTED_AFTER_WORD = re.compile(
    r"(?i)\b(?:" + _WORDS + r")\b[^\"'«»\n]{0,24}[\"'«]([^\"'»\n]*)[\"'»]"
)

_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Имя человека: забирается вся последовательность слов с заглавной буквы,
    # иначе в записи осталось бы отчество или фамилия.
    re.compile(
        r"(?i)\b(?:имя|фио|name|пациент\w*|пользовател\w*)\s*[:=]\s*"
        r"[^\s,;]+(?:\s+[А-ЯЁA-Z][\w-]*)*"
    ),
    re.compile(r"(?i)\b(?:" + _WORDS + r")\s*[:=]\s*[^\s,;]+"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}"),
)


def _keep_label(fragment: str) -> str:
    """Оставить название поля, скрыв значение: запись остаётся осмысленной."""
    for separator in (":", "="):
        head, sep, _tail = fragment.partition(separator)
        if sep:
            return f"{head}{sep} {REDACTED}"
    return REDACTED


class SensitiveDataFilter(logging.Filter):
    """Убирает из записей то, что относится к человеку, а не к работе программы.

    Фильтр применяется к уже собранному тексту записи, поэтому действует и на
    отладочном уровне: включение подробностей не должно открывать доступ к
    содержанию ответов.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — неверный формат не должен рвать журнал
            return True

        cleaned = _QUOTED_AFTER_WORD.sub(self._hide_quoted, message)
        for pattern in _SENSITIVE_PATTERNS:
            cleaned = pattern.sub(lambda m: _keep_label(m.group(0)), cleaned)

        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True

    @staticmethod
    def _hide_quoted(match: re.Match[str]) -> str:
        value = match.group(1)
        if not value:
            return match.group(0)
        return match.group(0).replace(value, REDACTED, 1)


def resolve_level(raw: str | None = None) -> int:
    """Уровень подробности из переменной окружения.

    По умолчанию обычный уровень: отладочный включается вручную на время
    разбора неисправности и сам по себе ничего лишнего в журнал не добавляет.
    """
    value = (
        raw if raw is not None else os.getenv("NEURO_MIRROR_LOG_LEVEL", "")
    ).strip().lower()
    return LEVELS.get(value, logging.INFO)


def restrict_directory_access(directory: Path) -> bool:
    """Закрыть каталог журналов для посторонних учётных записей.

    Возвращает признак успеха. Неудача не препятствует работе программы: вести
    журнал важнее, чем ограничить права на него, а о самой неудаче остаётся
    запись в нём же.
    """
    if sys.platform != "win32":
        try:
            directory.chmod(0o700)
            return True
        except OSError:
            return False

    account = os.getenv("USERNAME") or ""
    if not account:
        return False
    try:
        subprocess.run(
            [
                "icacls", str(directory),
                "/inheritance:r",
                "/grant", f"{account}:(OI)(CI)F",
                # Встроенная группа администраторов задаётся кодом, а не именем:
                # в русской и английской Windows имена различаются.
                "/grant", "*S-1-5-32-544:(OI)(CI)F",
            ],
            check=True, capture_output=True, timeout=20,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def configure_logging(
    *,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    level: int | None = None,
    console: bool = True,
    console_stream=None,
) -> Path:
    """Настроить журнал и вернуть путь к файлу.

    ``console_stream`` задаётся явно там, где стандартный вывод занят обменом
    с интерфейсом: диагностика в нём сделала бы поток нечитаемым.
    """
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    restricted = restrict_directory_access(directory)

    path = directory / LOG_FILE_NAME
    resolved = resolve_level() if level is None else level

    root = logging.getLogger()
    root.setLevel(resolved)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT)
    redaction = SensitiveDataFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler(console_stream or sys.stderr)
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redaction)
        root.addHandler(stream_handler)

    if not restricted:
        logging.getLogger(__name__).warning(
            "не удалось ограничить доступ к каталогу журналов %s", directory
        )
    return path

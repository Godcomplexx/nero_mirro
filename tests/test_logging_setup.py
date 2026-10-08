"""Технический журнал: объём, детализация, отсутствие персональных данных."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from neuro_mirror.core.access_journal import (
    EXPORT_RESULTS,
    VIEW_RESULTS,
    AccessJournal,
)


def journal_lines(journal: AccessJournal) -> list[dict]:
    """Прочитать журнал так, как его читает администратор: построчно."""
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line]
from neuro_mirror.core.logging_setup import (
    BACKUP_COUNT,
    MAX_BYTES,
    REDACTED,
    SensitiveDataFilter,
    configure_logging,
    resolve_level,
)


def record(message: str, *args) -> str:
    """Пропустить запись через фильтр и вернуть то, что попадёт в файл."""
    item = logging.LogRecord("t", logging.INFO, "", 0, message, args, None)
    SensitiveDataFilter().filter(item)
    return item.getMessage()


# ── Персональные данные ───────────────────────────────────────────────────────

@pytest.mark.parametrize("message, args", [
    ("hads_test: не распознан ответ из %r", ("мне тревожно почти всё время",)),
    ('moca: транскрипция: "лицо бархат церковь фиалка"', ()),
    ('speech: ответ = "да, конечно"', ()),
    ("профиль создан, имя: Иванов Иван Иванович", ()),
    ("уведомление отправлено на ivanov@mail.ru", ()),
    ("в анкете указан телефон +7 999 123-45-67", ()),
])
def test_personal_data_never_reaches_the_journal(message, args):
    """Ответы, имена и контакты — сведения о здоровье, им в журнале не место."""
    assert REDACTED in record(message, *args)


@pytest.mark.parametrize("message", [
    "moca_test: задание 3 из 11 завершено",
    "vision: лицо в кадре, качество 0.87",
    "gm02: игра начата, стимулов 5",
    "speech_worker: модель загружена за 4.2 с",
])
def test_technical_records_are_kept_intact(message):
    """Фильтр не должен обесценивать журнал: разбирать неисправность по нему."""
    assert record(message) == message


def test_the_field_name_survives_so_the_record_stays_readable():
    """Понятно, что именно скрыто, — иначе запись бесполезна."""
    assert record('moca: транскрипция: "лицо бархат"').startswith("moca: транскрипция:")


def test_broken_format_does_not_break_logging():
    item = logging.LogRecord("t", logging.INFO, "", 0, "нет аргумента %s %s", ("один",), None)
    assert SensitiveDataFilter().filter(item) is True


# ── Уровень детализации ───────────────────────────────────────────────────────

def test_default_level_is_the_ordinary_one():
    assert resolve_level("") == logging.INFO
    assert resolve_level("что-то непонятное") == logging.INFO


@pytest.mark.parametrize("value, expected", [
    ("errors", logging.ERROR),
    ("normal", logging.INFO),
    ("debug", logging.DEBUG),
    ("DEBUG", logging.DEBUG),
])
def test_level_is_chosen_by_name(value, expected):
    assert resolve_level(value) == expected


def test_debug_level_still_hides_personal_data(tmp_path):
    """Включение подробностей не должно открывать содержание ответов."""
    configure_logging(log_dir=tmp_path, level=logging.DEBUG, console=False)
    logging.getLogger("t").debug('ответ: "мне тревожно"')
    logging.shutdown()
    text = (Path(tmp_path) / "neuro_mirror.log").read_text(encoding="utf-8")
    assert "тревожно" not in text
    assert REDACTED in text


# ── Объём ─────────────────────────────────────────────────────────────────────

def test_journal_does_not_grow_without_limit(tmp_path):
    """Без ограничения журнал растёт, пока не кончится место на диске."""
    assert MAX_BYTES == 10 * 1024 * 1024
    assert BACKUP_COUNT == 5
    path = configure_logging(log_dir=tmp_path, console=False)
    handler = next(
        h for h in logging.getLogger().handlers if hasattr(h, "maxBytes")
    )
    assert handler.maxBytes == MAX_BYTES
    assert handler.backupCount == BACKUP_COUNT
    assert path.parent == Path(tmp_path)


def test_rotation_replaces_the_file_instead_of_extending_it(tmp_path):
    configure_logging(log_dir=tmp_path, console=False)
    handler = next(h for h in logging.getLogger().handlers if hasattr(h, "maxBytes"))
    handler.maxBytes = 900  # порог занижен, чтобы не писать десять мегабайт
    for index in range(200):
        logging.getLogger("t").info("запись номер %d с некоторым текстом", index)
    logging.shutdown()
    files = sorted(Path(tmp_path).glob("neuro_mirror.log*"))
    assert len(files) > 1, "файл не сменился при достижении предела"
    assert len(files) <= BACKUP_COUNT + 1, "старые файлы не удаляются"


# ── Журнал обращений к результатам ────────────────────────────────────────────

def test_access_journal_records_who_looked_and_when(tmp_path):
    journal = AccessJournal(tmp_path / "access.jsonl")
    journal.record(action=VIEW_RESULTS, user_id="u0001", details={"count": 3})
    journal.record(action=EXPORT_RESULTS, user_id="u0001")
    entries = journal_lines(journal)
    assert [e["action"] for e in entries] == [VIEW_RESULTS, EXPORT_RESULTS]
    assert all(e["user_id"] == "u0001" and e["at"] for e in entries)


def test_access_journal_is_append_only(tmp_path):
    """Журнал доступа, который можно переписать задним числом, бесполезен."""
    path = tmp_path / "access.jsonl"
    journal = AccessJournal(path)
    journal.record(action=VIEW_RESULTS, user_id="u0001")
    first = path.read_text(encoding="utf-8")
    journal.record(action=VIEW_RESULTS, user_id="u0002")
    assert path.read_text(encoding="utf-8").startswith(first)


def test_access_journal_keeps_no_result_content(tmp_path):
    journal = AccessJournal(tmp_path / "access.jsonl")
    journal.record(action=VIEW_RESULTS, user_id="u0001", details={"count": 2})
    entry = journal_lines(journal)[0]
    assert set(entry) <= {"at", "action", "user_id", "session_id", "account", "details"}
    assert entry["details"] == {"count": 2}


def test_write_failure_does_not_stop_the_program(tmp_path):
    """Человек должен увидеть свои результаты, даже если журнал недоступен."""
    journal = AccessJournal(tmp_path / "нет-такого-каталога" / "x" / "a.jsonl")
    journal.path = tmp_path  # запись в каталог невозможна
    journal.record(action=VIEW_RESULTS, user_id="u0001")  # не должно бросить

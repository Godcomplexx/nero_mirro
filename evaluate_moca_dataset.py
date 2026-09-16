"""Проверка текущего голосового MoCA на размеченных аудиозаписях.

Сценарий вырезает ответы по markers_*.json, распознаёт их тем же
``runtime.speech_worker.worker``, который использует приложение, и сравнивает
автоматические баллы с голосовыми пунктами актуальной экспертной таблицы.
"""

from __future__ import annotations

import csv
import datetime
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

# Окружение GigaAM пока собрано на Python 3.10, где ещё нет
# datetime.UTC. Этот алиас позволяет запустить оценку тем же ASR.
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # type: ignore[attr-defined]

import soundfile as sf
from tqdm import tqdm

from neuro_mirror.core.settings import Settings
from neuro_mirror.plugins.moca_test.plugin import MOCA_TASKS
from neuro_mirror.screening.moca_scoring import score_moca_tasks
from runtime.speech_worker.worker import transcribe_audio_file


# CONFIG ---------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "moca_validated_dataset" / "records"
REFERENCE_XLSX = (
    PROJECT_DIR
    / "moca_validated_dataset"
    / "Таблица MoCA_валидные записи.xlsx"
)
OUTPUT_DIR = PROJECT_DIR / "moca_evaluation_validated_40"

# В обновлённой таблице ID указан полностью и совпадает с именем папки.
REFERENCE_TO_SUBJECT_OFFSET = 0
EXPECTED_SEGMENT_COUNT = len(MOCA_TASKS)

# None — обработать все записи, для которых есть эталон в Excel.
MAX_SUBJECTS: int | None = None
# Каноническая таблица уже содержит только 40 проверенных ID.
SUBJECT_IDS: tuple[int, ...] | None = None
# Повторно использовать уже полученные транскрипции после прерванного запуска.
RESUME_FROM_CACHE = True
# ID, для которых нужно обновить аудиосегменты и ASR, сохранив остальной кэш.
FORCE_RETRANSCRIBE_SUBJECT_IDS: tuple[int, ...] = ()
# ---------------------------------------------------------------------------


REFERENCE_COLUMNS = {
    "attention_digits": "E",
    "attention_serial": "F",
    "language_sentences": "G",
    "language_fluency": "H",
    "abstraction": "I",
    "delayed_recall": "J",
}
REFERENCE_ID_COLUMN = "D"
FULL_MOCA_TOTAL_COLUMN = "K"

SCORED_REFERENCE_COMPONENTS = tuple(REFERENCE_COLUMNS)


def _column_name(cell_reference: str) -> str:
    """Получить буквенную часть Excel-адреса, например D из D17."""
    match = re.match(r"[A-Z]+", cell_reference)
    return match.group(0) if match else ""


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    """Прочитать первый лист XLSX средствами стандартной библиотеки."""
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path) as archive:
        strings_root = ElementTree.fromstring(
            archive.read("xl/sharedStrings.xml")
        )
        shared_strings = [
            "".join(node.text or "" for node in item.iter(f"{{{namespace}}}t"))
            for item in strings_root
        ]
        sheet_root = ElementTree.fromstring(
            archive.read("xl/worksheets/sheet1.xml")
        )

    rows: list[dict[str, str]] = []
    row_tag = f".//{{{namespace}}}sheetData/{{{namespace}}}row"
    for row in sheet_root.findall(row_tag):
        values: dict[str, str] = {}
        for cell in row.findall(f"{{{namespace}}}c"):
            value_node = cell.find(f"{{{namespace}}}v")
            if value_node is None or value_node.text is None:
                value = ""
            elif cell.get("t") == "s":
                value = shared_strings[int(value_node.text)]
            else:
                value = value_node.text
            values[_column_name(cell.get("r", ""))] = value
        rows.append(values)
    return rows


def load_references(path: Path) -> dict[int, dict[str, int]]:
    """Загрузить экспертные баллы голосовой части MoCA из Excel."""
    references: dict[int, dict[str, int]] = {}
    for row in _xlsx_rows(path)[2:]:
        match = re.search(r"\d+", row.get(REFERENCE_ID_COLUMN, ""))
        if not match:
            continue
        if not any(
            row.get(column, "").strip()
            for column in REFERENCE_COLUMNS.values()
        ):
            continue
        reference_id = int(match.group())
        subject_id = reference_id + REFERENCE_TO_SUBJECT_OFFSET
        scores = {
            task_id: int(float(row.get(column, "0") or 0))
            for task_id, column in REFERENCE_COLUMNS.items()
        }
        scores["voice_observed_total"] = sum(scores.values())
        scores["voice_total"] = sum(
            scores[task_id] for task_id in SCORED_REFERENCE_COMPONENTS
        )
        full_total = row.get(FULL_MOCA_TOTAL_COLUMN, "0") or "0"
        try:
            scores["full_moca_total"] = int(float(full_total))
        except ValueError:
            # В старых строках встречаются текстовые пометки вместо балла.
            scores["full_moca_total"] = 0
        scores["reference_id"] = reference_id
        references[subject_id] = scores
    return references


def find_session(subject_id: int) -> tuple[Path, Path, Path]:
    """Найти единственную полноценную сессию участника."""
    sessions = sorted(path for path in (DATA_DIR / str(subject_id)).iterdir()
                      if path.is_dir())
    complete_sessions: list[tuple[Path, Path, Path]] = []
    for session in sessions:
        audio_files = [
            path for path in session.glob("audio_*.wav")
            if not path.stem.endswith("_out")
        ]
        marker_files = [
            path for path in session.glob("markers_*.json")
            if "_before_fix_" not in path.stem
        ]
        if len(audio_files) != 1 or len(marker_files) != 1:
            continue
        try:
            segments = load_segments(marker_files[0])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if len(segments) == EXPECTED_SEGMENT_COUNT:
            complete_sessions.append(
                (session, audio_files[0], marker_files[0])
            )

    if len(complete_sessions) != 1:
        raise ValueError(
            f"Для участника {subject_id} найдено полных сессий: "
            f"{len(complete_sessions)}"
        )
    return complete_sessions[0]


def load_segments(marker_path: Path) -> list[tuple[float, float]]:
    """Собрать пары start/end в порядке номеров сегментов."""
    payload = json.loads(marker_path.read_text(encoding="utf-8"))
    by_number: dict[int, dict[str, float]] = {}
    for marker in payload.get("markers", []):
        number = int(marker["segment"])
        by_number.setdefault(number, {})[str(marker["type"])] = float(
            marker["time"]
        )

    segments = []
    for number in sorted(by_number):
        bounds = by_number[number]
        if "start" not in bounds or "end" not in bounds:
            raise ValueError(f"У сегмента {number} нет полной пары start/end")
        if bounds["end"] <= bounds["start"]:
            raise ValueError(f"У сегмента {number} неположительная длительность")
        segments.append((bounds["start"], bounds["end"]))
    return segments


def extract_segment(
    audio_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    """Вырезать участок WAV без загрузки всей записи в память."""
    with sf.SoundFile(audio_path) as source:
        start_frame = max(0, round(start_seconds * source.samplerate))
        end_frame = min(len(source), round(end_seconds * source.samplerate))
        source.seek(start_frame)
        audio = source.read(end_frame - start_frame, dtype="float32")
        sf.write(output_path, audio, source.samplerate, subtype="PCM_16")


def transcribe_segment(path: Path, settings: Settings) -> dict[str, Any]:
    """Запустить штатную функцию распознавания приложения."""
    return transcribe_audio_file(
        audio_path=str(path),
        model_name=settings.stt_model_name,
        language=settings.stt_language,
        device=settings.stt_device,
        compute_type=settings.stt_compute_type,
        beam_size=settings.stt_beam_size,
        best_of=settings.stt_best_of,
        vad_filter=settings.stt_vad_filter,
        hotwords=settings.stt_hotwords,
    )


def automated_components(scored_tasks: list[dict[str, Any]]) -> dict[str, int]:
    """Привести девять оцениваемых заданий к столбцам B–G Excel."""
    scores = {
        str(task["task_id"]): int(task.get("score") or 0)
        for task in scored_tasks
    }
    return {
        "attention_digits": (
            scores["attention_digits_forward"]
            + scores["attention_digits_backward"]
        ),
        "attention_serial": scores["attention_serial"],
        "language_sentences": (
            scores["language_sentence_1"] + scores["language_sentence_2"]
        ),
        "language_fluency": scores["language_fluency"],
        "abstraction": (
            scores["abstraction_1"] + scores["abstraction_2"]
        ),
        "delayed_recall": scores["delayed_recall"],
    }


def build_comparison(
    subject_id: int,
    reference: dict[str, int],
    session: str,
    scored_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Сравнить шесть оценок обновлённой таблицы без проб памяти."""
    automatic = automated_components(scored_tasks)
    task_matches = {
        task_id: automatic[task_id] == reference[task_id]
        for task_id in REFERENCE_COLUMNS
    }
    automatic_voice_total = sum(
        automatic[task_id] for task_id in SCORED_REFERENCE_COMPONENTS
    )
    recognized_task_count = sum(
        bool(str(task.get("transcript") or "").strip())
        for task in scored_tasks
    )
    return {
        "subject_id": subject_id,
        "reference_id": reference["reference_id"],
        "session": session,
        "reference_voice_observed_total": reference["voice_observed_total"],
        "automatic_voice_observed_total": sum(automatic.values()),
        "reference_voice_total": reference["voice_total"],
        "automatic_voice_total": automatic_voice_total,
        "difference": automatic_voice_total - reference["voice_total"],
        "reference_full_moca_total": reference["full_moca_total"],
        "exact_total_match": automatic_voice_total == reference["voice_total"],
        "matched_components": sum(task_matches.values()),
        "component_count": len(task_matches),
        "recognized_task_count": recognized_task_count,
        "usable_for_comparison": recognized_task_count > 0,
        "reference_components": {
            key: reference[key] for key in REFERENCE_COLUMNS
        },
        "automatic_components": automatic,
        "component_matches": task_matches,
        "tasks": scored_tasks,
    }


def save_json(path: Path, payload: Any) -> None:
    """Атомарно сохранить промежуточный или итоговый JSON."""
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def evaluate_subject(
    subject_id: int,
    reference: dict[str, int],
    settings: Settings,
) -> dict[str, Any]:
    """Распознать и оценить одну запись."""
    session, audio_path, marker_path = find_session(subject_id)
    segments = load_segments(marker_path)
    if len(segments) != EXPECTED_SEGMENT_COUNT:
        raise ValueError(
            f"ожидалось {EXPECTED_SEGMENT_COUNT} сегментов, найдено "
            f"{len(segments)}"
        )

    subject_dir = OUTPUT_DIR / "segments" / str(subject_id)
    subject_dir.mkdir(parents=True, exist_ok=True)
    tasks: list[dict[str, Any]] = []
    for task, (start, end) in tqdm(
        zip(MOCA_TASKS, segments),
        total=EXPECTED_SEGMENT_COUNT,
        desc=f"MoCA {subject_id}",
        unit="сегмент",
        leave=False,
    ):
        clip_path = subject_dir / f"{task.task_id}.wav"
        extract_segment(audio_path, clip_path, start, end)
        asr = transcribe_segment(clip_path, settings)
        tasks.append(
            {
                "task_id": task.task_id,
                "domain": task.domain,
                "transcript": str(asr.get("transcript") or "").strip(),
                "start_seconds": start,
                "end_seconds": end,
                "confidence_score": asr.get("confidence_score"),
                "transcribe_ms": asr.get("transcribe_ms"),
            }
        )

    scoring = score_moca_tasks(tasks)
    return build_comparison(
        subject_id,
        reference,
        str(session),
        scoring["tasks"],
    )


def write_csv(results: list[dict[str, Any]], path: Path) -> None:
    """Сохранить компактную таблицу сравнения по участникам."""
    columns = [
        "subject_id",
        "reference_id",
        "reference_voice_total",
        "automatic_voice_total",
        "reference_voice_observed_total",
        "automatic_voice_observed_total",
        "difference",
        "exact_total_match",
        "matched_components",
        "component_count",
        "recognized_task_count",
        "usable_for_comparison",
        "reference_full_moca_total",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=";")
        writer.writeheader()
        for result in results:
            writer.writerow({key: result.get(key) for key in columns})


def print_statistics(
    results: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    """Вывести итоговую статистику обработки и совпадений."""
    usable_results = [
        item for item in results if item.get("usable_for_comparison", True)
    ]
    unusable_count = len(results) - len(usable_results)
    exact = sum(bool(item["exact_total_match"]) for item in usable_results)
    component_matches = sum(
        item["matched_components"] for item in usable_results
    )
    component_total = sum(item["component_count"] for item in usable_results)
    mean_absolute_error = (
        sum(abs(item["difference"]) for item in usable_results)
        / len(usable_results)
        if usable_results else 0.0
    )
    print("\nОбработка завершена")
    print(f"Успешно обработано записей: {len(results)}")
    print(f"Пропущено с ошибкой разметки/файлов: {len(errors)}")
    print(f"Записей без распознанной речи: {unusable_count}")
    print(
        "Точное совпадение итогового балла: "
        f"{exact}/{len(usable_results)}"
    )
    print(
        "Совпадение голосовых компонентов B–K: "
        f"{component_matches}/{component_total}"
    )
    print(f"Средняя абсолютная ошибка итогового балла: {mean_absolute_error:.2f}")
    print(f"Подробный результат: {OUTPUT_DIR / 'results.json'}")
    print(f"Краткая таблица: {OUTPUT_DIR / 'summary.csv'}")


def main() -> None:
    """Выполнить полный прогон доступной сопоставимой части набора."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = OUTPUT_DIR / "results.json"
    references = load_references(REFERENCE_XLSX)
    subject_ids = sorted(references)
    if SUBJECT_IDS is not None:
        subject_ids = [
            subject_id
            for subject_id in subject_ids
            if subject_id in SUBJECT_IDS
        ]
    if MAX_SUBJECTS is not None:
        subject_ids = subject_ids[:MAX_SUBJECTS]

    cached_results: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    if RESUME_FROM_CACHE and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_results = {
            int(item["subject_id"]): item
            for item in cached.get("results", [])
        }
        # Пересчитать сравнение из сохранённых транскрипций. Это позволяет
        # менять метрики без повторного запуска длительного ASR.
        cached_results = {
            subject_id: build_comparison(
                subject_id,
                references[subject_id],
                str(item.get("session") or ""),
                score_moca_tasks(list(item["tasks"]))["tasks"],
            )
            for subject_id, item in cached_results.items()
            if (
                subject_id in references
                and item.get("tasks")
                and subject_id not in FORCE_RETRANSCRIBE_SUBJECT_IDS
            )
        }
        errors = list(cached.get("errors", []))
        errors = [
            item
            for item in errors
            if int(item.get("subject_id", -1)) not in cached_results
        ]

    settings = Settings.from_env()
    print(
        "ASR: "
        f"{settings.stt_model_name}, {settings.stt_device}, "
        f"{settings.stt_compute_type}"
    )
    for subject_id in tqdm(subject_ids, desc="Участники", unit="запись"):
        if subject_id in cached_results:
            continue
        try:
            result = evaluate_subject(
                subject_id,
                references[subject_id],
                settings,
            )
            cached_results[subject_id] = result
            errors = [
                item
                for item in errors
                if int(item.get("subject_id", -1)) != subject_id
            ]
        except Exception as exc:  # Ошибка одной записи не останавливает прогон.
            errors = [
                item for item in errors
                if int(item.get("subject_id", -1)) != subject_id
            ]
            errors.append({"subject_id": subject_id, "error": str(exc)})

        save_json(
            cache_path,
            {
                "results": [
                    cached_results[key] for key in sorted(cached_results)
                ],
                "errors": errors,
            },
        )

    # Сохранить очищенный список ошибок, даже если весь ASR взят из кэша.
    save_json(
        cache_path,
        {
            "results": [
                cached_results[key] for key in sorted(cached_results)
            ],
            "errors": errors,
        },
    )

    results = [cached_results[key] for key in sorted(cached_results)]
    write_csv(results, OUTPUT_DIR / "summary.csv")
    print_statistics(results, errors)


if __name__ == "__main__":
    main()

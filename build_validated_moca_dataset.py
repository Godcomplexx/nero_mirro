"""Собрать канонический набор проверенных записей MoCA внутри проекта."""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from tqdm import tqdm

from evaluate_moca_dataset import automated_components
from neuro_mirror.screening.moca_scoring import score_moca_tasks


# CONFIG ---------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
SOURCE_DATA_DIR = Path(r"C:\Users\1\Desktop\ДАННЫЕ МОКА")
SOURCE_TABLE = SOURCE_DATA_DIR / "Таблица MoCA_испытуемые.xlsx"
TARGET_DIR = PROJECT_DIR / "moca_validated_dataset"
BUILD_DIR = PROJECT_DIR / "moca_validated_dataset_building"

OLD_BASELINE_EVALUATION = (
    PROJECT_DIR
    / "moca_evaluation_updated_no_memory"
    / "model_comparison"
    / "gigaam_char"
    / "evaluation.json"
)
OLD_BASELINE_SUMMARY = (
    PROJECT_DIR
    / "moca_evaluation_updated_no_memory"
    / "model_comparison"
    / "model_summary.csv"
)
OLD_SOURCE_RESULTS = (
    PROJECT_DIR / "moca_evaluation_updated_no_memory" / "results.json"
)
NEW_EVALUATION = (
    PROJECT_DIR / "moca_evaluation_corrected_v2_133_145" / "results.json"
)

OUTPUT_TABLE_NAME = "Таблица MoCA_валидные записи.xlsx"
COPY_BUFFER_SIZE = 8 * 1024 * 1024
# ---------------------------------------------------------------------------


COMPONENT_NAMES = (
    "attention_digits",
    "attention_serial",
    "language_sentences",
    "language_fluency",
    "abstraction",
    "delayed_recall",
)


def load_json(path: Path) -> dict[str, Any]:
    """Прочитать JSON в UTF-8."""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_evaluation(
    rows: list[dict[str, Any]],
    title: str,
) -> dict[str, int]:
    """Убедиться, что текущий оценщик полностью совпадает с эталоном."""
    component_total = 0
    component_matches = 0
    exact_subjects = 0
    errors = []

    for item in rows:
        scored = score_moca_tasks(list(item["tasks"]))["tasks"]
        automatic = automated_components(scored)
        reference = item["reference_components"]
        subject_errors = []
        for component in COMPONENT_NAMES:
            component_total += 1
            if automatic[component] == reference[component]:
                component_matches += 1
            else:
                subject_errors.append(
                    {
                        "component": component,
                        "automatic": automatic[component],
                        "reference": reference[component],
                    }
                )
        if subject_errors:
            errors.append(
                {
                    "subject_id": item["subject_id"],
                    "errors": subject_errors,
                }
            )
        else:
            exact_subjects += 1

    if errors:
        raise RuntimeError(
            f"Набор {title} больше не совпадает с эталоном: {errors}"
        )
    return {
        "subject_count": len(rows),
        "exact_subjects": exact_subjects,
        "component_matches": component_matches,
        "component_total": component_total,
    }


def find_current_marker(session_dir: Path) -> Path:
    """Найти единственный актуальный markers JSON, исключив резервные копии."""
    candidates = [
        path
        for path in session_dir.glob("markers_*.json")
        if "backup" not in path.name.lower()
        and "_before_" not in path.name.lower()
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"В {session_dir} ожидался один актуальный markers JSON, "
            f"найдено: {len(candidates)}"
        )
    return candidates[0]


def validate_markers(path: Path) -> int:
    """Проверить наличие 11 полных пар границ сегментов."""
    payload = load_json(path)
    segments: dict[int, set[str]] = {}
    for marker in payload.get("markers", []):
        number = int(marker["segment"])
        segments.setdefault(number, set()).add(str(marker["type"]))
    expected = set(range(1, 12))
    if set(segments) != expected:
        raise RuntimeError(f"Неверный набор сегментов в {path}: {segments}")
    incomplete = [
        number
        for number, marker_types in segments.items()
        if marker_types != {"start", "end"}
    ]
    if incomplete:
        raise RuntimeError(f"Неполные пары маркеров в {path}: {incomplete}")
    return len(segments)


def collect_session_files(session_dir: Path) -> list[Path]:
    """Выбрать полную запись и только актуальную разметку."""
    audio = list(session_dir.glob("audio_*.wav"))
    video = list(session_dir.glob("video_*.avi"))
    user_info = session_dir / "user_info.json"
    marker = find_current_marker(session_dir)
    if len(audio) != 1:
        raise RuntimeError(f"В {session_dir} найдено WAV: {len(audio)}")
    if len(video) > 1:
        raise RuntimeError(f"В {session_dir} найдено AVI: {len(video)}")
    if not user_info.is_file():
        raise RuntimeError(f"Нет user_info.json в {session_dir}")
    validate_markers(marker)
    return [audio[0], *video, marker, user_info]


def copy_with_sha256(
    source: Path,
    destination: Path,
    progress: tqdm,
) -> str:
    """Скопировать файл и одновременно посчитать контрольную сумму."""
    digest = hashlib.sha256()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_file, destination.open("wb") as output_file:
        while chunk := input_file.read(COPY_BUFFER_SIZE):
            output_file.write(chunk)
            digest.update(chunk)
            progress.update(len(chunk))
    shutil.copystat(source, destination)
    return digest.hexdigest()


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Прочитать общие строки XLSX."""
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{{{namespace}}}t"))
        for item in root
    ]


def cell_value(
    cell: ElementTree.Element,
    shared_strings: list[str],
    namespace: str,
) -> str:
    """Получить строковое значение ячейки XLSX."""
    value_node = cell.find(f"{{{namespace}}}v")
    if value_node is None or value_node.text is None:
        return ""
    if cell.get("t") == "s":
        return shared_strings[int(value_node.text)]
    return value_node.text


def create_filtered_xlsx(
    source: Path,
    destination: Path,
    valid_ids: set[int],
) -> None:
    """Создать XLSX только с валидными участниками, сохранив оформление."""
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ElementTree.register_namespace("", namespace)
    with zipfile.ZipFile(source, "r") as input_archive:
        shared_strings = read_shared_strings(input_archive)
        sheet_name = "xl/worksheets/sheet1.xml"
        sheet_root = ElementTree.fromstring(input_archive.read(sheet_name))
        sheet_data = sheet_root.find(f"{{{namespace}}}sheetData")
        if sheet_data is None:
            raise RuntimeError("В таблице не найден sheetData")

        kept_rows = []
        for row in list(sheet_data):
            row_number = int(row.get("r", "0"))
            if row_number <= 2:
                kept_rows.append(row)
                continue
            id_cell = next(
                (
                    cell
                    for cell in row.findall(f"{{{namespace}}}c")
                    if re.match(r"D\d+", cell.get("r", ""))
                ),
                None,
            )
            raw_id = (
                cell_value(id_cell, shared_strings, namespace)
                if id_cell is not None
                else ""
            )
            try:
                subject_id = int(float(raw_id))
            except ValueError:
                continue
            if subject_id in valid_ids:
                kept_rows.append(row)

        if len(kept_rows) != len(valid_ids) + 2:
            raise RuntimeError(
                "Число строк итоговой таблицы не совпало с числом ID: "
                f"{len(kept_rows) - 2} != {len(valid_ids)}"
            )

        for row in list(sheet_data):
            sheet_data.remove(row)
        for new_number, row in enumerate(kept_rows, start=1):
            row.set("r", str(new_number))
            for cell in row.findall(f"{{{namespace}}}c"):
                reference = cell.get("r", "")
                column = re.match(r"[A-Z]+", reference)
                if column:
                    cell.set("r", f"{column.group(0)}{new_number}")
            sheet_data.append(row)

        dimension = sheet_root.find(f"{{{namespace}}}dimension")
        if dimension is not None:
            dimension.set("ref", f"A1:R{len(kept_rows)}")
        sheet_bytes = ElementTree.tostring(
            sheet_root,
            encoding="utf-8",
            xml_declaration=True,
        )

        with zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as output_archive:
            for item in input_archive.infolist():
                content = (
                    sheet_bytes
                    if item.filename == sheet_name
                    else input_archive.read(item.filename)
                )
                output_archive.writestr(item, content)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    """Сохранить читаемый JSON."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    """Собрать, проверить и атомарно опубликовать набор."""
    if TARGET_DIR.exists():
        raise FileExistsError(f"Целевая папка уже существует: {TARGET_DIR}")
    if BUILD_DIR.exists():
        raise FileExistsError(
            f"Осталась незавершённая сборка: {BUILD_DIR}"
        )

    old_payload = load_json(OLD_BASELINE_EVALUATION)
    new_payload = load_json(NEW_EVALUATION)
    old_rows = list(old_payload["comparisons"])
    new_rows = list(new_payload["results"])
    old_metrics = validate_evaluation(old_rows, "старый эталон")
    new_metrics = validate_evaluation(new_rows, "новые записи")

    old_source_rows = {
        int(item["subject_id"]): item
        for item in load_json(OLD_SOURCE_RESULTS)["results"]
    }
    new_source_rows = {
        int(item["subject_id"]): item for item in new_rows
    }
    valid_ids = sorted(
        {int(item["subject_id"]) for item in old_rows}
        | set(new_source_rows)
    )
    if len(valid_ids) != 40:
        raise RuntimeError(f"Ожидалось 40 валидных ID, получено {len(valid_ids)}")

    sessions = []
    all_source_files = []
    for subject_id in valid_ids:
        source_item = (
            new_source_rows.get(subject_id)
            or old_source_rows.get(subject_id)
        )
        if source_item is None:
            raise RuntimeError(f"Не найдена исходная сессия ID {subject_id}")
        session_name = Path(str(source_item["session"])).name
        session_dir = SOURCE_DATA_DIR / str(subject_id) / session_name
        if not session_dir.is_dir():
            raise FileNotFoundError(f"Нет сессии: {session_dir}")
        files = collect_session_files(session_dir)
        sessions.append((subject_id, session_name, session_dir, files))
        all_source_files.extend(files)

    total_bytes = sum(path.stat().st_size for path in all_source_files)
    BUILD_DIR.mkdir(parents=True)
    records = []
    try:
        with tqdm(
            total=total_bytes,
            desc="Копирование валидного набора",
            unit="B",
            unit_scale=True,
        ) as progress:
            for subject_id, session_name, session_dir, files in sessions:
                target_session = (
                    BUILD_DIR / "records" / str(subject_id) / session_name
                )
                copied_files = []
                for source_file in files:
                    destination = target_session / source_file.name
                    checksum = copy_with_sha256(
                        source_file,
                        destination,
                        progress,
                    )
                    copied_files.append(
                        {
                            "name": source_file.name,
                            "size": source_file.stat().st_size,
                            "sha256": checksum,
                        }
                    )
                marker_path = find_current_marker(session_dir)
                records.append(
                    {
                        "subject_id": subject_id,
                        "session": session_name,
                        "segment_count": validate_markers(marker_path),
                        "files": copied_files,
                    }
                )

        table_path = BUILD_DIR / OUTPUT_TABLE_NAME
        create_filtered_xlsx(SOURCE_TABLE, table_path, set(valid_ids))

        validation_dir = BUILD_DIR / "validation"
        validation_dir.mkdir()
        shutil.copy2(
            OLD_BASELINE_EVALUATION,
            validation_dir / "old_baseline_evaluation.json",
        )
        shutil.copy2(
            OLD_BASELINE_SUMMARY,
            validation_dir / "old_baseline_model_summary.csv",
        )
        shutil.copy2(
            NEW_EVALUATION,
            validation_dir / "new_evaluation_133_145.json",
        )

        manifest = {
            "schema_version": 1,
            "created_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "description": (
                "Канонический набор записей MoCA, полностью совпавший "
                "с экспертной разметкой текущим пайплайном."
            ),
            "record_count": len(records),
            "valid_subject_ids": valid_ids,
            "total_data_bytes": total_bytes,
            "table": OUTPUT_TABLE_NAME,
            "validation": {
                "old_baseline": old_metrics,
                "new_records": new_metrics,
                "combined": {
                    "subject_count": len(records),
                    "exact_subjects": (
                        old_metrics["exact_subjects"]
                        + new_metrics["exact_subjects"]
                    ),
                    "component_matches": (
                        old_metrics["component_matches"]
                        + new_metrics["component_matches"]
                    ),
                    "component_total": (
                        old_metrics["component_total"]
                        + new_metrics["component_total"]
                    ),
                },
            },
            "records": records,
        }
        save_json(BUILD_DIR / "manifest.json", manifest)
        (BUILD_DIR / "README.md").write_text(
            "# Валидированный набор MoCA\n\n"
            "Канонический набор из 40 записей, проверенный текущим "
            "пайплайном: 40/40 точных итогов и 240/240 компонентов.\n\n"
            "- `records/` — исходные WAV, AVI, сведения об участнике и "
            "актуальный JSON разметки.\n"
            f"- `{OUTPUT_TABLE_NAME}` — единая экспертная таблица только "
            "для валидных ID.\n"
            "- `manifest.json` — состав набора, результаты проверки, "
            "размеры и SHA-256.\n"
            "- `validation/` — отчёты старого и нового эталонных "
            "прогонов.\n",
            encoding="utf-8",
        )
        BUILD_DIR.replace(TARGET_DIR)
    except Exception:
        print(f"Незавершённая сборка сохранена для диагностики: {BUILD_DIR}")
        raise

    print("\nСборка завершена")
    print(f"Записей: {len(records)}")
    print(f"Файлов данных: {len(all_source_files)}")
    print(f"Объём данных: {total_bytes / (1024 ** 3):.2f} ГиБ")
    print("Точные итоги: 40/40")
    print("Совпавшие компоненты: 240/240")
    print(f"Папка: {TARGET_DIR}")


if __name__ == "__main__":
    main()

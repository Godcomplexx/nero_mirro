"""Динамика для отчёта специалиста.

«Методология скрининга» 2.0, раздел 8: динамика считается раздельно и в один
балл не склеивается.

* Аудио-MoCA — разница «последний − входной» по сумме и по каждому домену.
* HADS — разница по каждой подшкале как контекст для когнитивной динамики:
  если за время курса изменилась выраженность тревоги или депрессии, это
  отмечается рядом с динамикой аудио-MoCA.
* Динамика показывается только при сопоставимых условиях: та же версия
  правил оценки, достоверные сессии. Несопоставимость не скрывается, а
  называется.
* Пока воспроизводимость не подтверждена, динамика описательная: улучшение не
  называется эффектом тренировок, ухудшение — прогрессированием.

Входной тест — тот, по которому открыт курс тренировок. Если курса нет или
после входного теста нового ещё не было, последний тест сравнивается с
предыдущим. Ситуационная задача в динамику не входит: модуль не реализован.

Эффект научения («Методика подбора и оценки тренировочного курса», 8.3):
у форм GM-11, GM-13, GM-16 и GM-24 механика как в аудио-MoCA. Если балл
домена вырос, а в курсе проходились такие формы этого домена, рядом с
изменением ставится оговорка о возможном эффекте научения.
"""
from __future__ import annotations

from typing import Any

from neuro_mirror.screening.data_quality import assess

NOTE = (
    "Динамика описательная: улучшение не называется эффектом тренировок, "
    "ухудшение — прогрессированием (Методология скрининга, раздел 8)."
)
HADS_NOTE = "Изменение HADS — контекст для динамики аудио-MoCA, а не самостоятельный показатель."


def _by_time(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("stored_at") or ""))


def _point(item: dict[str, Any], score: Any, max_score: Any) -> dict[str, Any]:
    return {
        "session_id": item.get("session_id"),
        "stored_at": item.get("stored_at"),
        "score": score,
        "max_score": max_score,
    }


def _change(before: Any, after: Any) -> int | None:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return after - before
    return None


def _comparability(first: dict[str, Any], last: dict[str, Any]) -> list[str]:
    """Почему пару нельзя сравнивать напрямую; пусто — сопоставима."""
    notes = []
    if str(first.get("scenario_version") or "") != str(last.get("scenario_version") or ""):
        notes.append(
            "Разные версии правил оценки: "
            f"{first.get('scenario_version') or 'не указана'} и {last.get('scenario_version') or 'не указана'}."
        )
    for label, item in (("входная", first), ("последняя", last)):
        if assess(item)["limited"]:
            notes.append(f"{label.capitalize()} сессия с ограничением интерпретации (качество данных).")
    return notes


def _learning_notes(domains: list[dict[str, Any]], analogs: list[dict[str, Any]] | None) -> list[str]:
    notes = []
    for row in domains:
        change = row.get("change")
        if not isinstance(change, (int, float)) or change <= 0:
            continue
        shown = [item for item in analogs or [] if item.get("domain") == row.get("domain") and item.get("passes")]
        if not shown:
            continue
        forms = ", ".join(f"{item['game_code']} — {item['passes']}" for item in shown)
        notes.append(
            f"Домен «{row['domain']}»: балл вырос, а в курсе проходились формы с механикой "
            f"как в аудио-MoCA ({forms} раз). Возможен эффект научения."
        )
    return notes


def _moca_dynamics(
    moca: list[dict[str, Any]],
    entry_session_id: str | None,
    analogs: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    ordered = _by_time(moca)
    if len(ordered) < 2:
        return None
    last = ordered[-1]
    entry = next((item for item in ordered if entry_session_id and item.get("session_id") == entry_session_id), None)
    first = entry if entry is not None and entry is not last else ordered[-2]
    first_domains = {row.get("domain"): row for row in (first.get("domains") or {}).get("moca_domains") or []}
    last_domains = {row.get("domain"): row for row in (last.get("domains") or {}).get("moca_domains") or []}
    domains = []
    for name, after in last_domains.items():
        before = first_domains.get(name) or {}
        domains.append({
            "domain": name,
            "from": before.get("score"),
            "to": after.get("score"),
            "max_score": after.get("max_score"),
            "change": _change(before.get("score"), after.get("score")),
        })
    first_score = (first.get("domains") or {}).get("moca_score")
    last_score = (last.get("domains") or {}).get("moca_score")
    notes = _comparability(first, last)
    return {
        "from": _point(first, first_score, (first.get("domains") or {}).get("moca_max_score")),
        "to": _point(last, last_score, (last.get("domains") or {}).get("moca_max_score")),
        "total_change": _change(first_score, last_score),
        "domains": domains,
        "comparable": not notes,
        "comparability_notes": notes,
        "learning_notes": _learning_notes(domains, analogs),
    }


def _hads_dynamics(hads: list[dict[str, Any]], baseline_at: str | None) -> dict[str, Any] | None:
    ordered = [
        item for item in _by_time(hads)
        if (item.get("domains") or {}).get("hads_anxiety_score") is not None
    ]
    if len(ordered) < 2:
        return None
    # Входной HADS — последний не позже входного MoCA: он описывает то же
    # состояние, на фоне которого открывался курс.
    before_baseline = [item for item in ordered if baseline_at and str(item.get("stored_at") or "") <= baseline_at]
    first = before_baseline[-1] if before_baseline else ordered[0]
    last = ordered[-1]
    if last is first:
        return None
    result = {"from": _point(first, None, None), "to": _point(last, None, None), "note": HADS_NOTE}
    for scale in ("anxiety", "depression"):
        key = f"hads_{scale}_score"
        before = (first.get("domains") or {}).get(key)
        after = (last.get("domains") or {}).get(key)
        result[scale] = {"from": before, "to": after, "change": _change(before, after)}
    return result


def dynamics(
    items: list[dict[str, Any]],
    *,
    entry_session_id: str | None = None,
    moca_analogs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Динамика MoCA и контекст HADS по сохранённым результатам пользователя.

    ``moca_analogs`` — сколько раз в курсе пройдены формы-аналоги аудио-MoCA
    (``course_report.moca_analogs``): по ним ставится оговорка о научении.
    """
    moca = [item for item in items if item.get("report_type") == "moca"]
    hads = [item for item in items if item.get("report_type") in ("hads", "screening")]
    moca_dynamics = _moca_dynamics(moca, entry_session_id, moca_analogs)
    baseline_at = moca_dynamics["from"]["stored_at"] if moca_dynamics else None
    return {
        "moca": moca_dynamics,
        "hads": _hads_dynamics(hads, baseline_at),
        "note": NOTE,
    }

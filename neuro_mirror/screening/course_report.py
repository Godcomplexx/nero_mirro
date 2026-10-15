"""Отчёты специалиста о занятии и о курсе тренировок, уведомления.

«Методика подбора и оценки тренировочного курса» v2:

* 8.2 — отчёт о занятии: по каждому заданию форма, уровень, стимульный
  набор, успешность, время, статус завершения, досрочное выполнение;
  переходы уровней; отметки; паузы (число, длительность), прерывания и их
  причины; самочувствие до и после занятия;
* 8.3 — отчёт о курсе: траектория уровня по каждой форме за 12 занятий,
  сравнение успешности 6-го и 12-го занятий (только на одном уровне и на
  наборе 3), регулярность, число прохождений форм-аналогов аудио-MoCA,
  нормированный дефицит D по доменам и обязательная подпись;
* 9 — уведомления специалисту: больше двух неполных занятий, красные флаги,
  все формы домена с отметкой «трудная» (6.3), устойчивое падение
  успешности.

Здесь только расчёт по сохранённому курсу; ничего не записывается.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from neuro_mirror.plugins.games.catalog import GAME_CATALOG
from neuro_mirror.screening.difficulty_policy import FLAG_HARD, Success, has_levels
from neuro_mirror.screening.moca_scoring import MOCA_MODULES

TRAINING_NOTE = (
    "Тренировочная динамика отражает выполнение упражнений, а не изменение "
    "когнитивного статуса. Динамику когнитивного статуса показывает выходной скрининг."
)

# Формы, у которых механика «как в аудио-MoCA» (4.4, обязательное правило 3;
# 8.3). Домен — ведущий домен формы в каталоге.
MOCA_ANALOGS = ("GM-11", "GM-13", "GM-16", "GM-24")

# Сравнение 6-го и 12-го занятий (6.5, 8.3)
COMPARE_SESSIONS = (6, 12)
COMPARE_SET_NUMBER = 3

# Уведомления (раздел 9; пороги — предложение методики, менять здесь)
INCOMPLETE_SESSIONS_LIMIT = 2
DROP_PASSES = 3          # три прохождения формы подряд — два падения
DROP_MIN_FORMS = 2       # «по нескольким формам»
DROP_MIN_DOMAINS = 2     # «разных доменов»

DOMAIN_LABELS = {str(module["id"]): str(module["label"]) for module in MOCA_MODULES}
LEADING_DOMAIN = {item.code: DOMAIN_LABELS.get(item.primary_domain.value, item.primary_domain.value) for item in GAME_CATALOG}
TITLES = {item.code: item.title for item in GAME_CATALOG}

SESSION_DONE = ("completed", "incomplete")


def _moment(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _seconds(start: Any, end: Any) -> float | None:
    a, b = _moment(start), _moment(end)
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds())


def _success(item: dict[str, Any]) -> Success | None:
    raw = item.get("success")
    return Success(**raw) if isinstance(raw, dict) else None


def _rate(success: Success | None) -> float | None:
    if success is None or success.total <= 0:
        return None
    return round(success.correct / success.total, 3)


# ---- 8.2. Отчёт о занятии ----


def _pauses(session: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for pause in session.get("pauses") or []:
        rows.append({
            "position": pause.get("position"),
            "trial": pause.get("trial"),
            "paused_at": pause.get("paused_at"),
            "seconds": _seconds(pause.get("paused_at"), pause.get("ended_at")),
            "ended_by": pause.get("ended_by"),
        })
    return rows


def _active_seconds(item: dict[str, Any], pauses: list[dict[str, Any]]) -> float | None:
    """Активное время задания: от начала до конца без пауз внутри него (4.5, п. 4)."""
    total = _seconds(item.get("started_at"), item.get("finished_at"))
    if total is None:
        return None
    paused = sum(
        pause["seconds"] or 0.0
        for pause in pauses
        if pause["position"] == item.get("position") and pause["seconds"] is not None
    )
    return round(max(0.0, total - paused), 1)


def _early(item: dict[str, Any], active: float | None) -> dict[str, Any] | None:
    """Досрочное выполнение: задание с лимитом времени выполнено до его конца."""
    limit = item.get("time_limit_ms")
    if not limit:
        return None
    done_in_time = item.get("status") == "done" and item.get("end_reason") == "done"
    return {
        "early": bool(done_in_time),
        "limit_seconds": round(float(limit) / 1000),
        "active_seconds": active,
    }


def session_report(session: dict[str, Any], san: list[dict[str, Any]], course_id: str) -> dict[str, Any]:
    """Отчёт специалиста о занятии (8.2)."""
    pauses = _pauses(session)
    games = []
    for item in session.get("games") or []:
        active = _active_seconds(item, pauses)
        reason = item.get("interruption_reason") or {}
        games.append({
            "position": item.get("position"),
            "game_code": item.get("game_code"),
            "title": item.get("title"),
            "domain": item.get("domain"),
            "difficulty_level": item.get("difficulty_level"),
            "temporary_level": bool(item.get("temporary_level")),
            "adaptation": item.get("adaptation"),
            "stimulus_set": item.get("stimulus_set"),
            "stimulus_set_number": item.get("stimulus_set_number"),
            "randomization_seed": item.get("randomization_seed"),
            "status": item.get("status"),
            "u06_status": "abandoned" if item.get("status") == "abandoned" else item.get("u06_status"),
            "success": item.get("success"),
            "counted": item.get("counted"),
            "flags": list(item.get("flags") or []),
            "active_seconds": active,
            "early_completion": _early(item, active),
            "interruption_reason": reason.get("label"),
            "alternative_for": item.get("alternative_for"),
            "replaced_by": item.get("replaced_by"),
            "attempts": item.get("attempts"),
            "resumed": item.get("resumed") or 0,
        })
    key = f"{course_id}-{session.get('number')}"
    feeling = {
        moment: next((entry for entry in san if entry.get("session_id") == key and entry.get("moment") == moment), None)
        for moment in ("before", "after")
    }
    interruption = session.get("interruption") or {}
    return {
        "games": games,
        "pauses": pauses,
        "pause_count": len(pauses),
        "pause_seconds": round(sum(row["seconds"] or 0.0 for row in pauses), 1),
        "san_before": feeling["before"],
        "san_after": feeling["after"],
        "pre_check": session.get("pre_check"),
        "interruption": interruption.get("label"),
        "order": session.get("order"),
    }


# ---- 8.3. Отчёт о курсе ----


def _shown_items(course: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Пары «занятие — задание» по порядку курса."""
    return [
        (session, item)
        for session in course.get("sessions") or []
        for item in session.get("games") or []
    ]


def trajectory(course: dict[str, Any]) -> list[dict[str, Any]]:
    """Траектория уровня каждой формы по занятиям — основной показатель (8.3)."""
    by_form: dict[str, dict[str, Any]] = {}
    for session, item in _shown_items(course):
        if item.get("status") not in ("done", "abandoned"):
            continue
        code = item["game_code"]
        row = by_form.setdefault(code, {
            "game_code": code,
            "title": item.get("title") or TITLES.get(code, code),
            "domain": item.get("domain"),
            "adaptation": item.get("adaptation"),
            "points": [],
        })
        success = _success(item)
        row["points"].append({
            "session": session.get("number"),
            "level": item.get("difficulty_level"),
            "temporary_level": bool(item.get("temporary_level")),
            "status": item.get("status"),
            "u06_status": item.get("u06_status"),
            "success": item.get("success"),
            "rate": _rate(success),
            "counted": item.get("counted"),
            "stimulus_set_number": item.get("stimulus_set_number"),
        })
    return sorted(by_form.values(), key=lambda row: (str(row["domain"]), row["game_code"]))


def compare_6_and_12(course: dict[str, Any]) -> dict[str, Any]:
    """Сравнение успешности 6-го и 12-го занятий (8.3).

    Только формы, которые в обоих занятиях шли на одном уровне и на наборе
    3: успешность на разных уровнях несопоставима. По остальным — причина.
    """
    first, last = COMPARE_SESSIONS
    passes: dict[int, dict[str, dict[str, Any]]] = {first: {}, last: {}}
    for session, item in _shown_items(course):
        number = session.get("number")
        if number in passes and item.get("status") == "done" and item.get("alternative_for") is None:
            passes[number][item["game_code"]] = item
    rows, other = [], []
    for code in sorted(set(passes[first]) | set(passes[last])):
        a, b = passes[first].get(code), passes[last].get(code)
        title = (a or b or {}).get("title") or TITLES.get(code, code)
        if a is None or b is None:
            other.append({"game_code": code, "title": title, "reason": f"формы не было в {first if a is None else last}-м занятии"})
            continue
        if a.get("difficulty_level") != b.get("difficulty_level"):
            other.append({"game_code": code, "title": title,
                          "reason": f"разный уровень: {a.get('difficulty_level')} и {b.get('difficulty_level')}"})
            continue
        if a.get("stimulus_set_number") != COMPARE_SET_NUMBER or b.get("stimulus_set_number") != COMPARE_SET_NUMBER:
            other.append({"game_code": code, "title": title, "reason": "стимульный набор не 3"})
            continue
        sa, sb = _success(a), _success(b)
        if not (a.get("counted") and b.get("counted")) or sa is None or sb is None:
            other.append({"game_code": code, "title": title, "reason": "прохождение не учитывается"})
            continue
        rows.append({
            "game_code": code,
            "title": title,
            "level": a.get("difficulty_level"),
            "session_6": sa.to_dict(),
            "session_12": sb.to_dict(),
            "rate_6": _rate(sa),
            "rate_12": _rate(sb),
        })
    return {"rows": rows, "not_comparable": other}


def regularity(course: dict[str, Any]) -> dict[str, Any]:
    sessions = course.get("sessions") or []
    count = {status: sum(1 for session in sessions if session.get("status") == status)
             for status in ("completed", "incomplete", "in_progress", "planned")}
    items = [item for _, item in _shown_items(course)]
    pauses = [pause for session in sessions for pause in _pauses(session)]
    return {
        **count,
        "interrupted_tasks": sum(1 for item in items if item.get("status") == "abandoned"),
        "alternatives": sum(1 for item in items if item.get("alternative_for") is not None),
        "pauses": len(pauses),
        "pause_seconds": round(sum(pause["seconds"] or 0.0 for pause in pauses), 1),
        "red_flags": len(course.get("red_flags") or []),
    }


def moca_analogs(course: dict[str, Any]) -> list[dict[str, Any]]:
    """Сколько раз пройдены формы-аналоги аудио-MoCA (8.3)."""
    counts = {code: 0 for code in MOCA_ANALOGS}
    for _, item in _shown_items(course):
        if item.get("game_code") in counts and item.get("status") == "done":
            counts[item["game_code"]] += 1
    return [
        {"game_code": code, "title": TITLES.get(code, code), "domain": LEADING_DOMAIN.get(code), "passes": count}
        for code, count in counts.items()
    ]


def normalized_deficit(profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Нормированный дефицит D = (M − S) / M по входному профилю (3.1)."""
    rows = []
    for row in profile or []:
        score, maximum = row.get("score"), row.get("max_score")
        if not isinstance(score, (int, float)) or not isinstance(maximum, (int, float)) or maximum <= 0:
            continue
        rows.append({
            "domain": row.get("domain"),
            "score": score,
            "max_score": maximum,
            "deficit": round((maximum - score) / maximum, 2),
        })
    return rows


def course_summary(course: dict[str, Any] | None) -> dict[str, Any] | None:
    """Отчёт о курсе (8.3)."""
    if course is None:
        return None
    return {
        "trajectory": trajectory(course),
        "compare_6_12": compare_6_and_12(course),
        "regularity": regularity(course),
        "moca_analogs": moca_analogs(course),
        "deficit": normalized_deficit((course.get("entry") or {}).get("profile") or []),
        "note": TRAINING_NOTE,
    }


# ---- 9. Уведомления специалисту ----


def _sustained_drops(course: dict[str, Any]) -> list[dict[str, Any]]:
    """Формы, у которых успешность падала два прохождения подряд.

    Сравниваются только учитываемые прохождения на одном уровне: смена уровня
    меняет и успешность. Последнее из трёх прохождений — в одном из двух
    последних закрытых занятий, иначе падение давнее.
    """
    closed = [s["number"] for s in course.get("sessions") or [] if s.get("status") in SESSION_DONE]
    recent_sessions = set(closed[-2:])
    by_form: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for session, item in _shown_items(course):
        if item.get("status") == "done" and item.get("counted") and item.get("alternative_for") is None:
            by_form.setdefault(item["game_code"], []).append((session["number"], item))
    drops = []
    for code, passes in by_form.items():
        if len(passes) < DROP_PASSES:
            continue
        last = passes[-DROP_PASSES:]
        if last[-1][0] not in recent_sessions:
            continue
        if len({item.get("difficulty_level") for _, item in last}) != 1:
            continue
        rates = [_success(item) for _, item in last]
        if any(rate is None for rate in rates):
            continue
        falling = all(
            later.correct * earlier.total < earlier.correct * later.total
            for earlier, later in zip(rates, rates[1:])
        )
        if falling:
            drops.append({
                "game_code": code,
                "domain": last[-1][1].get("domain"),
                "sessions": [number for number, _ in last],
                "rates": [_rate(rate) for rate in rates],
            })
    return drops


def notifications(course: dict[str, Any] | None, levels: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Уведомления специалисту по курсу (раздел 9; 6.3, граничные случаи)."""
    if course is None:
        return []
    found: list[dict[str, Any]] = []
    hold = course.get("hold")
    for flag in course.get("red_flags") or []:
        found.append({
            "kind": "red_flag",
            "urgent": True,
            "at": flag.get("at"),
            "text": (
                f"Красный флаг: {flag.get('detail')}"
                + (f" (занятие {flag['session_number']})" if flag.get("session_number") else "")
                + ". Пользователю рекомендовано обратиться к врачу."
            ),
        })
    if hold:
        found.append({
            "kind": "hold",
            "urgent": True,
            "at": hold.get("since"),
            "text": "Курс приостановлен до решения специалиста. Снять приостановку можно в этом отчёте.",
        })
    entry = course.get("entry") or {}
    confirmed = {row.get("domain") for row in entry.get("confirmed") or []}
    for domain in entry.get("low_confidence") or []:
        if domain in confirmed:
            continue
        found.append({
            "kind": "low_confidence",
            "urgent": False,
            "domain": domain,
            "text": (
                f"Домен «{domain}»: низкая достоверность входного результата. Пока результат не "
                "подтверждён, в занятиях у домена только обязательное задание (методика, 4.2, п. 6). "
                "Прослушайте ответы в отчёте когнитивного теста и подтвердите результат."
            ),
        })
    incomplete = [s["number"] for s in course.get("sessions") or [] if s.get("status") == "incomplete"]
    if len(incomplete) > INCOMPLETE_SESSIONS_LIMIT:
        found.append({
            "kind": "incomplete_sessions",
            "urgent": False,
            "text": f"Неполных занятий: {len(incomplete)} (занятия {', '.join(map(str, incomplete))}).",
        })
    hard = {code for code, state in (levels or {}).items() if FLAG_HARD in (state.get("flags") or [])}
    by_domain: dict[str, list[str]] = {}
    for item in GAME_CATALOG:
        if has_levels(item.code):
            by_domain.setdefault(LEADING_DOMAIN[item.code], []).append(item.code)
    for domain, codes in sorted(by_domain.items()):
        if codes and all(code in hard for code in codes):
            found.append({
                "kind": "domain_hard",
                "urgent": False,
                "text": f"Все формы домена «{domain}» с отметкой «трудная» ({', '.join(codes)}): пересмотрите курс.",
            })
    drops = _sustained_drops(course)
    if len(drops) >= DROP_MIN_FORMS and len({row["domain"] for row in drops}) >= DROP_MIN_DOMAINS:
        forms = ", ".join(f"{row['game_code']} ({' → '.join(str(rate) for rate in row['rates'])})" for row in drops)
        found.append({
            "kind": "sustained_drop",
            "urgent": False,
            "text": (
                f"Успешность падает два прохождения подряд по формам разных доменов: {forms}. "
                "Это не красный флаг — динамику стоит обсудить."
            ),
            "forms": drops,
        })
    return found

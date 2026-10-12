"""Качество данных сессии и ограничение интерпретации результата.

ТЗ: «Формулировки результатов… при низком качестве данных — явное
ограничение интерпретации»; «Отображение пользователю/специалисту
ограничений результата при низком качестве данных».

Методология скрининга 2.0:

* раздел 6.1 — нераспознанный ответ получает 0 баллов; это правило
  обработки ошибки распознавания, а не доказательство неверного ответа.
  Число и доля нераспознанных ответов идут в отчёт специалиста. Если в
  домене нераспознанных ответов ``LOW_CONFIDENCE_THRESHOLD`` и больше, домен
  помечается «низкая достоверность», и специалисту предлагается прослушать
  транскрипт или провести пробу повторно. Порог 2 — рабочее предложение для
  апробации, не норма;
* раздел 4 — отсутствие лица в кадре и низкое качество видео фиксируются
  как событие качества данных и учитываются при оценке достоверности.

Оценка строится по сохранённому отчёту, поэтому отметки появляются и у
результатов, записанных раньше. Пользователю — понятная фраза без
клинических терминов, специалисту — подробности и что сделать.
"""
from __future__ import annotations

from typing import Any

LOW_CONFIDENCE_THRESHOLD = 2

LOW_CONFIDENCE = "низкая достоверность"

VIDEO_ISSUE_TEXT = {
    "no_frames": "кадры с камеры не получены",
    "unreadable_frame": "кадр не удалось разобрать",
    "no_face": "лицо не было видно в кадре",
    "face_too_small": "лицо было слишком далеко от камеры",
    "detector_unavailable": "детектор лиц был недоступен",
}

USER_ADVICE = "Обсудите результат со специалистом; при необходимости тест можно пройти ещё раз."


def _issue_codes(domains: dict[str, Any]) -> list[str]:
    codes = []
    for issue in domains.get("video_quality_issues") or []:
        code = issue if isinstance(issue, str) else (issue or {}).get("code")
        if code and code not in codes:
            codes.append(str(code))
    return codes


def unrecognized_answers(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Оцениваемые задания без распознанной речи — всего и по доменам."""
    scored = [task for task in tasks if (task.get("max_score") or 0) > 0]
    missing = [task for task in scored if not str(task.get("transcript") or "").strip()]
    by_domain: dict[str, int] = {}
    for task in missing:
        domain = str(task.get("domain") or "")
        by_domain[domain] = by_domain.get(domain, 0) + 1
    return {"count": len(missing), "total": len(scored), "by_domain": by_domain}


def assess(item: dict[str, Any]) -> dict[str, Any]:
    """Качество данных одного сохранённого результата.

    Возвращает ``limited`` — ограничена ли интерпретация, причины для
    специалиста, фразу для пользователя и домены с низкой достоверностью.
    """
    domains = item.get("domains") or {}
    summary = item.get("summary") or {}
    report_type = item.get("report_type")
    reasons: list[str] = []
    # То же для пользователя — простыми словами, без клинических терминов
    user: list[str] = []
    low_confidence: list[str] = []
    unrecognized = None

    conditions = str(summary.get("limitations") or "").strip()
    if conditions:
        reasons.append(conditions)
        user.append(conditions)

    if report_type == "moca":
        unrecognized = unrecognized_answers(list(domains.get("moca_tasks") or []))
        if unrecognized["count"]:
            reasons.append(
                f"Не распознано ответов: {unrecognized['count']} из {unrecognized['total']}; "
                "за них поставлено 0 баллов — это ошибка распознавания, а не доказательство неверного ответа."
            )
        low_confidence = sorted(
            domain for domain, count in unrecognized["by_domain"].items()
            if domain and count >= LOW_CONFIDENCE_THRESHOLD
        )
        if low_confidence:
            reasons.append(
                f"«{LOW_CONFIDENCE.capitalize()}»: {', '.join(low_confidence)}. "
                "Прослушайте транскрипт или проведите пробу повторно."
            )
            sections = ", ".join(f"«{domain}»" for domain in low_confidence)
            where = "в разделе" if len(low_confidence) == 1 else "в разделах"
            user.append(
                f"Часть ответов не удалось распознать, поэтому результат {where} {sections} "
                "может быть неточным."
            )
        elif unrecognized["count"]:
            user.append("Некоторые ответы не удалось распознать, поэтому результат может быть неточным.")

    codes = _issue_codes(domains)
    if codes:
        reasons.append(
            "Качество видео: " + "; ".join(VIDEO_ISSUE_TEXT.get(code, code) for code in codes) + "."
        )
        user.append("Камера не всё время хорошо видела лицо.")

    if report_type == "screening" and domains.get("heart_rate_bpm") is None \
            and domains.get("heart_rate_status") not in (None, "disabled"):
        reasons.append("Пульс по видео измерить не удалось.")
        user.append("Пульс измерить не удалось.")

    answered = domains.get("hads_answered_count")
    total = domains.get("hads_question_count")
    if answered is not None and total and answered < total:
        reasons.append(f"Опросник HADS заполнен не полностью: {answered} из {total} ответов.")
        user.append("Опросник заполнен не полностью.")

    limited = bool(reasons)
    return {
        "limited": limited,
        "reasons": reasons,
        "low_confidence_domains": low_confidence,
        "unrecognized": unrecognized,
        "user_text": " ".join(user + [USER_ADVICE]) if limited else "",
    }

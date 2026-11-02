"""Pilot implementation of the social-everyday situational task.

Only approved narrative passports are loaded here.  They remain marked as
``demo_only`` and disabled for automatic screening until the specialist
selection, interruption rules and prerecorded audio are implemented.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


SCENARIO = "situational_task_demo"
INITIAL_STEP = "intro"
FINAL_STEP = "completed"
DEFERRED_STEP = "deferred"
NOT_CONDUCTED_STEP = "not_conducted"
DEMO_DIRECTORY = Path(__file__).resolve().parent / "assets" / "situational_task" / "memory"


class SituationalTaskError(ValueError):
    """The demo narrative or requested transition is invalid."""


def load_demo_narrative(
    narrative_id: str = "sbs-pam-01",
    *,
    directory: str | Path = DEMO_DIRECTORY,
) -> dict[str, Any]:
    path = Path(directory) / f"{narrative_id.replace('-', '_')}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("id") != narrative_id:
        raise SituationalTaskError("Идентификатор нарратива не совпадает с именем файла.")
    if data.get("demo_only") is not True or data.get("enabled_in_screening") is not False:
        raise SituationalTaskError("Демонстрационный нарратив должен быть отключён для скрининга.")
    for key in ("story", "image", "orientation_questions", "image_questions", "memory_questions", "scoring"):
        if not data.get(key):
            raise SituationalTaskError(f"В демонстрационном нарративе отсутствует поле {key}.")
    if any(len(data[key]) != 4 for key in ("orientation_questions", "image_questions", "memory_questions")):
        raise SituationalTaskError("Для этапов ориентации, изображения и памяти требуется по четыре вопроса.")
    return data


def initial_checkpoint(narrative_id: str) -> dict[str, Any]:
    return {
        "source": SCENARIO,
        "narrative_id": narrative_id,
        "step": INITIAL_STEP,
        "question_index": 0,
        "current_prompt_level": 0,
        "responses": {
            "retelling": "",
            "retelling_addition": "",
            "orientation": [],
            "image_description": "",
            "image_description_addition": "",
            "image_questions": [],
            "memory": [],
        },
        "prompt_levels": [],
        "preparation": {
            "readiness": None,
            "glasses_ready": None,
            "hearing_attempts": 0,
            "hearing_status": None,
        },
    }


def advance(
    checkpoint: dict[str, Any],
    narrative: dict[str, Any],
    *,
    action: str,
    value: str = "",
) -> tuple[dict[str, Any], bool]:
    """Apply one valid UI action and return ``(checkpoint, completed)``."""
    state = deepcopy(checkpoint)
    responses = state.setdefault("responses", {})
    step = str(state.get("step") or INITIAL_STEP)
    value = str(value or "").strip()

    preparation = state.setdefault("preparation", {})
    if step == "readiness" and action == "defer":
        preparation["readiness"] = "deferred"
        state["step"] = DEFERRED_STEP
        return state, True
    if step == "hearing" and action == "hearing_bad":
        attempts = int(preparation.get("hearing_attempts") or 0) + 1
        preparation["hearing_attempts"] = attempts
        preparation["hearing_status"] = "bad"
        if attempts >= 2:
            state["step"] = NOT_CONDUCTED_STEP
            return state, True
        return state, False

    simple = {
        "intro": ("begin", "readiness"),
        "readiness": ("continue_now", "glasses"),
        "glasses": ("glasses_ready", "hearing"),
        "hearing": ("hearing_good", "story"),
        "story": ("story_heard", "retelling"),
    }
    if step in simple:
        expected, next_step = simple[step]
        if action != expected:
            raise SituationalTaskError("Действие не соответствует текущему этапу.")
        if step == "readiness":
            preparation["readiness"] = "continue"
        elif step == "glasses":
            preparation["glasses_ready"] = True
        elif step == "hearing":
            preparation["hearing_status"] = "good"
        state["step"] = next_step
        state["question_index"] = 0
        return state, False

    if step == "retelling":
        _require_answer(action, "submit_retelling", value)
        responses["retelling"] = value
        state["step"] = "retelling_addition"
        state["question_index"] = 0
        return state, False

    if step == "retelling_addition":
        if action not in {"submit_retelling_addition", "skip_retelling_addition"}:
            raise SituationalTaskError("Действие не соответствует текущему этапу.")
        responses["retelling_addition"] = value
        state["step"] = "orientation"
        state["question_index"] = 0
        return state, False

    question_steps = {
        "orientation": ("orientation_questions", "orientation", "image_description"),
        "image_questions": ("image_questions", "image_questions", "memory"),
        "memory": ("memory_questions", "memory", FINAL_STEP),
    }
    if step in question_steps:
        source_key, response_key, next_step = question_steps[step]
        if action == "request_prompt":
            if step != "memory":
                raise SituationalTaskError("Подсказки предусмотрены только на третьем шаге.")
            level = min(2, int(state.get("current_prompt_level") or 0) + 1)
            state["current_prompt_level"] = level
            state.setdefault("prompt_levels", []).append({
                "step": step,
                "question_index": int(state.get("question_index") or 0),
                "level": level,
            })
            return state, False
        _require_answer(action, "submit_answer", value)
        answers = responses.setdefault(response_key, [])
        index = int(state.get("question_index") or 0)
        expected_count = len(narrative[source_key])
        if index != len(answers) or index >= expected_count:
            raise SituationalTaskError("Нарушен порядок ответов на вопросы.")
        question_item = narrative[source_key][index]
        question_text = (
            str(question_item.get("question") or "")
            if isinstance(question_item, dict) else str(question_item)
        )
        answers.append({
            "question_index": index,
            "question": question_text,
            "answer": value,
            "prompt_level": int(state.get("current_prompt_level") or 0),
        })
        index += 1
        state["question_index"] = index
        state["current_prompt_level"] = 0
        if index >= expected_count:
            state["step"] = next_step
            state["question_index"] = 0
        return state, state.get("step") == FINAL_STEP

    if step == "image_description":
        _require_answer(action, "submit_image_description", value)
        responses["image_description"] = value
        state["step"] = "image_description_addition"
        state["question_index"] = 0
        return state, False

    if step == "image_description_addition":
        if action not in {"submit_image_description_addition", "skip_image_description_addition"}:
            raise SituationalTaskError("Действие не соответствует текущему этапу.")
        responses["image_description_addition"] = value
        state["step"] = "image_questions"
        state["question_index"] = 0
        return state, False

    if step in {FINAL_STEP, DEFERRED_STEP, NOT_CONDUCTED_STEP}:
        raise SituationalTaskError("Демонстрационная задача уже завершена.")
    raise SituationalTaskError("Неизвестный этап демонстрационной задачи.")


def public_state(session: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
    checkpoint = deepcopy(session.get("checkpoint") or initial_checkpoint(narrative["id"]))
    step = checkpoint.get("step", INITIAL_STEP)
    index = int(checkpoint.get("question_index") or 0)
    payload: dict[str, Any] = {
        "session_id": session.get("session_id"),
        "status": session.get("status"),
        "step": step,
        "question_index": index,
        "title": narrative.get("title", "Демонстрационная ситуационная задача"),
        "narrative_code": narrative.get("code", narrative.get("id")),
        "narrative_version": narrative.get("version"),
        "demo_only": True,
        "progress": _progress(step, index, narrative),
        "prompt_level": int(checkpoint.get("current_prompt_level") or 0),
        "preparation": deepcopy(checkpoint.get("preparation") or {}),
    }
    if step == "story":
        payload["story"] = narrative["story"]
    elif step == "orientation":
        payload["question"] = narrative["orientation_questions"][index]["question"]
        payload["question_count"] = len(narrative["orientation_questions"])
    elif step in {"image_description", "image_description_addition", "image_questions"}:
        payload["image_url"] = f"/api/situational-task/demo/assets/{narrative['image']}"
        if step == "image_questions":
            payload["question"] = narrative["image_questions"][index]
            payload["question_count"] = len(narrative["image_questions"])
    elif step == "memory":
        payload["question"] = narrative["memory_questions"][index]["question"]
        payload["question_count"] = len(narrative["memory_questions"])
    if step == "memory" and payload["prompt_level"]:
        item = narrative["memory_questions"][index]
        payload["prompt"] = (
            item.get("general_prompt") if payload["prompt_level"] == 1
            else item.get("category_prompt")
        )
    return payload


def result_from_checkpoint(
    checkpoint: dict[str, Any],
    narrative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome = (
        "deferred" if checkpoint.get("step") == DEFERRED_STEP
        else "not_conducted" if checkpoint.get("step") == NOT_CONDUCTED_STEP
        else "completed"
    )
    result = {
        "report_type": SCENARIO,
        "demo_only": True,
        "narrative_id": checkpoint.get("narrative_id"),
        "responses": deepcopy(checkpoint.get("responses") or {}),
        "preparation": deepcopy(checkpoint.get("preparation") or {}),
        "prompt_levels": deepcopy(checkpoint.get("prompt_levels") or []),
        "has_total_score": False,
        "specialist_confirmation_required": outcome == "completed",
        "outcome": outcome,
    }
    if narrative is not None and outcome == "completed":
        result["preliminary_scores"] = score_demo(checkpoint, narrative)
    return result


def score_demo(checkpoint: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
    """Transparent keyword scoring for the demonstration narrative only."""
    rules = narrative.get("scoring") or narrative.get("demo_scoring") or {}
    responses = checkpoint.get("responses") or {}
    retelling = " ".join(filter(None, [
        str(responses.get("retelling") or ""),
        str(responses.get("retelling_addition") or ""),
    ]))

    recall_evidence = []
    for rule in rules.get("recall_units") or []:
        core = rule.get("core") or rule.get("all") or []
        detail = rule.get("detail") or []
        found = _matches_all(retelling, core)
        detail_found = bool(detail) and _matches_all(retelling, detail)
        score = 2 if found and (detail_found or not detail) else 1 if found else 0
        recall_evidence.append({
            "label": rule.get("label"), "found": found,
            "detail_found": detail_found, "score": score,
        })
    recall_score = sum(item["score"] for item in recall_evidence)

    orientation_evidence, orientation_score = _score_questions(
        responses.get("orientation") or [], rules.get("orientation_rules") or [], points=1
    )

    description = " ".join(filter(None, [
        str(responses.get("image_description") or ""),
        str(responses.get("image_description_addition") or ""),
    ]))
    concept_evidence = []
    for rule in rules.get("image_concepts") or []:
        groups = rule.get("all") or []
        matched = sum(1 for group in groups if _matches_any(description, group))
        if groups and matched == len(groups):
            score = 3
        elif matched >= max(1, (len(groups) + 1) // 2):
            score = 2
        elif matched:
            score = 1
        else:
            score = 0
        concept_evidence.append({
            "label": rule.get("label"), "matched_groups": matched,
            "group_count": len(groups), "score": score,
        })
    description_score = sum(item["score"] for item in concept_evidence)

    image_answers = responses.get("image_questions") or []
    risk_text = str(image_answers[0].get("answer") or "") if image_answers else ""
    risk_rule = rules.get("risk_rule") or {}
    risk_full = _matches_any(risk_text, risk_rule.get("full") or risk_rule.get("strong") or [])
    risk_partial = _matches_any(risk_text, risk_rule.get("partial") or risk_rule.get("basic") or [])
    risk_score = 2 if risk_full else 1 if risk_partial else 0

    solution_text = " ".join(
        str(image_answers[index].get("answer") or "")
        for index in (1, 2) if len(image_answers) > index
    )
    has_passport_solution = bool(rules.get("solution_rule"))
    solution_rule = rules.get("solution_rule") or rules.get("action_rule") or {}
    solution_full = _matches_any(solution_text, solution_rule.get("full") or [])
    solution_partial = _matches_any(solution_text, solution_rule.get("partial") or [])
    if has_passport_solution:
        action_score = 2 if solution_full and solution_partial else 1 if solution_full or solution_partial else 0
    else:
        action_score = 2 if solution_full else 1 if solution_partial else 0
    first_action_text = str(image_answers[2].get("answer") or "") if len(image_answers) > 2 else ""
    contact_text = str(image_answers[3].get("answer") or "") if len(image_answers) > 3 else ""

    memory_evidence, memory_raw = _score_questions(
        responses.get("memory") or [], rules.get("memory_rules") or [], points=2,
        reduce_for_prompt=True,
    )
    return {
        "demo_only": True,
        "version": "pilot-passport-1",
        "recall": {"score": recall_score, "max_score": 20, "evidence": recall_evidence},
        "orientation": {"score": orientation_score, "max_score": 4, "evidence": orientation_evidence},
        "image_description": {"score": description_score, "max_score": 21, "evidence": concept_evidence},
        "risk_understanding": {"score": risk_score, "max_score": 2, "answer": risk_text},
        "practical_solution": {"score": action_score, "max_score": 2, "answer": solution_text},
        "first_action": {"present": _matches_any(first_action_text, rules.get("first_action_rule") or []), "answer": first_action_text},
        "knows_whom_to_contact": {"present": _matches_any(contact_text, rules.get("contact_rule") or []), "answer": contact_text},
        "dangerous_solution": {"present": _matches_any(solution_text, rules.get("dangerous_answers") or [])},
        "memory_attention": {"score": memory_raw, "max_score": 8, "evidence": memory_evidence},
        "distortions": None,
        "intrusions": None,
        "image_mixups": None,
        "note": "Предварительная оценка по паспорту нарратива; требуется подтверждение специалистом.",
    }


def _require_answer(action: str, expected_action: str, value: str) -> None:
    if action != expected_action:
        raise SituationalTaskError("Действие не соответствует текущему этапу.")
    if not value:
        raise SituationalTaskError("Введите демонстрационный ответ.")


def _progress(step: str, index: int, narrative: dict[str, Any]) -> dict[str, int]:
    order = [
        "intro", "readiness", "glasses", "hearing", "story", "retelling",
        "retelling_addition", "orientation", "image_description",
        "image_description_addition", "image_questions", "memory", FINAL_STEP,
    ]
    if step in {DEFERRED_STEP, NOT_CONDUCTED_STEP}:
        return {"current": 0, "total": (len(order) - 1) * 100}
    base = order.index(step) if step in order else 0
    if step == "orientation":
        base += index / len(narrative["orientation_questions"])
    elif step == "image_questions":
        base += index / len(narrative["image_questions"])
    elif step == "memory":
        base += index / len(narrative["memory_questions"])
    return {"current": round(base * 100), "total": (len(order) - 1) * 100}


def _normalized(text: str) -> str:
    return re.sub(r"[^а-яa-z0-9]+", " ", text.lower().replace("ё", "е")).strip()


def _matches_any(text: str, stems: list[str]) -> bool:
    normalized = _normalized(text)
    return any(_normalized(str(stem)) in normalized for stem in stems if str(stem).strip())


def _matches_all(text: str, groups: list[list[str]]) -> bool:
    return bool(groups) and all(_matches_any(text, list(group)) for group in groups)


def _score_questions(
    answers: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    *,
    points: int,
    reduce_for_prompt: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    evidence = []
    total = 0
    by_index = {int(item.get("question_index") or 0): item for item in answers}
    for index, rule in enumerate(rules):
        answer = by_index.get(index) or {}
        correct = _matches_all(str(answer.get("answer") or ""), rule.get("all") or [])
        awarded = points if correct else 0
        if correct and reduce_for_prompt and int(answer.get("prompt_level") or 0) > 0:
            awarded = max(1, points - 1)
        total += awarded
        evidence.append({
            "question_index": index,
            "answer": answer.get("answer", ""),
            "correct": correct,
            "prompt_level": int(answer.get("prompt_level") or 0),
            "score": awarded,
            "max_score": points,
        })
    return evidence, total

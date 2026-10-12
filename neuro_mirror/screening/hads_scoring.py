"""HADS (Hospital Anxiety and Depression Scale) — вопросы и подсчёт.

Источник: «Госпитальная Шкала Тревоги и Депрессии (HADS)».
14 утверждений: часть I — тревога (7), часть II — депрессия (7).
Каждому варианту ответа соответствует балл 0–3 (порядок баллов у вопросов
различается, поэтому балл хранится вместе с текстом варианта).

Интерпретация каждой подшкалы:
  0–7   — норма
  8–10  — субклинически выраженная тревога / депрессия
  11+   — клинически выраженная тревога / депрессия
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HadsOption:
    text: str
    score: int


@dataclass(frozen=True)
class HadsQuestion:
    question_id: str
    part: str  # "anxiety" | "depression"
    text: str
    options: tuple[HadsOption, ...]


HADS_QUESTIONS: tuple[HadsQuestion, ...] = (
    # ── Часть I: тревога ──────────────────────────────────────────────────────
    HadsQuestion(
        "anxiety_1", "anxiety",
        "Я испытываю напряжение, мне не по себе",
        (
            HadsOption("всё время", 3),
            HadsOption("часто", 2),
            HadsOption("время от времени, иногда", 1),
            HadsOption("совсем не испытываю", 0),
        ),
    ),
    HadsQuestion(
        "anxiety_2", "anxiety",
        "Я испытываю страх, кажется, что что-то ужасное может вот-вот случиться",
        (
            HadsOption("определённо это так, и страх очень велик", 3),
            HadsOption("да, это так, но страх не очень велик", 2),
            HadsOption("иногда, но это меня не беспокоит", 1),
            HadsOption("совсем не испытываю", 0),
        ),
    ),
    HadsQuestion(
        "anxiety_3", "anxiety",
        "Беспокойные мысли крутятся у меня в голове",
        (
            HadsOption("постоянно", 3),
            HadsOption("большую часть времени", 2),
            HadsOption("время от времени и не так часто", 1),
            HadsOption("только иногда", 0),
        ),
    ),
    HadsQuestion(
        "anxiety_4", "anxiety",
        "Я легко могу присесть и расслабиться",
        (
            HadsOption("определённо, это так", 0),
            HadsOption("наверно, это так", 1),
            HadsOption("лишь изредка, это так", 2),
            HadsOption("совсем не могу", 3),
        ),
    ),
    HadsQuestion(
        "anxiety_5", "anxiety",
        "Я испытываю внутреннее напряжение или дрожь",
        (
            HadsOption("совсем не испытываю", 0),
            HadsOption("иногда", 1),
            HadsOption("часто", 2),
            HadsOption("очень часто", 3),
        ),
    ),
    HadsQuestion(
        "anxiety_6", "anxiety",
        "Я испытываю неусидчивость, мне постоянно нужно двигаться",
        (
            HadsOption("определённо, это так", 3),
            HadsOption("наверно, это так", 2),
            HadsOption("лишь в некоторой степени, это так", 1),
            HadsOption("совсем не испытываю", 0),
        ),
    ),
    HadsQuestion(
        "anxiety_7", "anxiety",
        "У меня бывает внезапное чувство паники",
        (
            HadsOption("очень часто", 3),
            HadsOption("довольно часто", 2),
            HadsOption("не так уж часто", 1),
            HadsOption("совсем не бывает", 0),
        ),
    ),
    # ── Часть II: депрессия ───────────────────────────────────────────────────
    HadsQuestion(
        "depression_1", "depression",
        "То, что приносило мне большое удовольствие, и сейчас вызывает у меня такое же чувство",
        (
            HadsOption("определённо, это так", 0),
            HadsOption("наверное, это так", 1),
            HadsOption("лишь в очень малой степени, это так", 2),
            HadsOption("это совсем не так", 3),
        ),
    ),
    HadsQuestion(
        "depression_2", "depression",
        "Я способен рассмеяться и увидеть в том или ином событии смешное",
        (
            HadsOption("определённо, это так", 0),
            HadsOption("наверное, это так", 1),
            HadsOption("лишь в очень малой степени, это так", 2),
            HadsOption("совсем не способен", 3),
        ),
    ),
    HadsQuestion(
        "depression_3", "depression",
        "Я испытываю бодрость",
        (
            HadsOption("совсем не испытываю", 3),
            HadsOption("очень редко", 2),
            HadsOption("иногда", 1),
            HadsOption("практически всё время", 0),
        ),
    ),
    HadsQuestion(
        "depression_4", "depression",
        "Мне кажется, что я стал всё делать очень медленно",
        (
            HadsOption("практически всё время", 3),
            HadsOption("часто", 2),
            HadsOption("иногда", 1),
            HadsOption("совсем нет", 0),
        ),
    ),
    HadsQuestion(
        "depression_5", "depression",
        "Я не слежу за своей внешностью",
        (
            HadsOption("определённо, это так", 3),
            HadsOption("я не уделяю этому столько времени, сколько нужно", 2),
            HadsOption("может быть, я стал меньше уделять этому времени", 1),
            HadsOption("я слежу за собой так же, как и раньше", 0),
        ),
    ),
    HadsQuestion(
        "depression_6", "depression",
        "Я считаю, что мои дела (занятия, увлечения) могут принести мне чувство удовлетворения",
        (
            HadsOption("точно так же, как и обычно", 0),
            HadsOption("да, но не в той степени, как раньше", 1),
            HadsOption("значительно меньше, чем обычно", 2),
            HadsOption("совсем так не считаю", 3),
        ),
    ),
    HadsQuestion(
        "depression_7", "depression",
        "Я могу получить удовольствие от хорошей книги, радио- или телепрограммы",
        (
            HadsOption("часто", 0),
            HadsOption("иногда", 1),
            HadsOption("редко", 2),
            HadsOption("очень редко", 3),
        ),
    ),
)

PART_LABELS = {"anxiety": "Тревога", "depression": "Депрессия"}


def interpret_subscale(score: int) -> str:
    if score <= 7:
        return "норма"
    if score <= 10:
        return "субклинически выраженная"
    return "клинически выраженная"


def score_hads(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute subscale totals from answered questions.

    ``answers`` items: {question_id, part, option_index, option_text, score, method}.
    Unanswered questions are simply absent; ``complete`` reflects that.
    """
    anxiety = sum(a["score"] for a in answers if a.get("part") == "anxiety")
    depression = sum(a["score"] for a in answers if a.get("part") == "depression")
    answered = len(answers)
    total = len(HADS_QUESTIONS)
    complete = answered == total

    notes = "" if complete else (
        f"Отвечено {answered} из {total} вопросов — итог может быть занижен."
    )

    return {
        "anxiety_score": anxiety,
        "anxiety_max": 21,
        "anxiety_interpretation": interpret_subscale(anxiety) + " тревога",
        "depression_score": depression,
        "depression_max": 21,
        "depression_interpretation": interpret_subscale(depression) + " депрессия",
        "answered_count": answered,
        "question_count": total,
        "complete": complete,
        "notes": notes,
        "answers": answers,
    }

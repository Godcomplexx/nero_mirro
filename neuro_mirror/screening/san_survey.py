"""Краткий опросник самочувствия.

Шесть вопросов тремя блоками — самочувствие, активность, настроение, — по два
в каждом. Ответ выбирается из пяти состояний с текстовыми подписями.

Формулировки взяты из «Вопросы для субъективной оценки до и после сессии» и
не сокращаются: подписи у каждого вопроса свои и подобраны под его смысл, а
общая шкала «плохо — хорошо» теряет эту разницу. Общая шкала всё же
возвращается рядом с вопросами, потому что на неё опирается показ пиктограмм.

Опросник предъявляется до и после занятия, поэтому ответы хранятся вместе с
отметкой, когда он заполнен: сравнение «до» и «после» — и есть смысл этой
оценки.
"""
from __future__ import annotations

from typing import Any

QUESTIONNAIRE_VERSION = "1"

GROUP_WELLBEING = "Самочувствие"
GROUP_ACTIVITY = "Активность"
GROUP_MOOD = "Настроение"

# Когда опросник предъявляется.
MOMENT_BEFORE = "before"
MOMENT_AFTER = "after"
MOMENTS = (MOMENT_BEFORE, MOMENT_AFTER)

INTRO = (
    "Оцените, как вы чувствуете себя сейчас. "
    "Здесь нет правильных или неправильных ответов."
)

# Пять состояний от худшего к лучшему. Значения возрастают вместе с
# состоянием, поэтому суммировать ответы можно без пересчёта.
SCALE: tuple[dict[str, Any], ...] = (
    {"value": 1, "label": "Очень плохо"},
    {"value": 2, "label": "Плохо"},
    {"value": 3, "label": "Средне"},
    {"value": 4, "label": "Хорошо"},
    {"value": 5, "label": "Отлично"},
)

MIN_VALUE = SCALE[0]["value"]
MAX_VALUE = SCALE[-1]["value"]

QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "wellbeing_ready",
        "group": GROUP_WELLBEING,
        "text": "Вы сейчас готовы выполнять задания?",
        "options": ("Совсем не готов", "Скорее не готов", "Не совсем готов",
                    "Почти готов", "Полностью готов"),
    },
    {
        "id": "wellbeing_vigour",
        "group": GROUP_WELLBEING,
        "text": "Насколько бодро вы себя сейчас чувствуете?",
        "options": ("Совсем нет бодрости", "Мало бодрости", "Немного бодрости",
                    "Бодро", "Очень бодро"),
    },
    {
        "id": "activity_thinking",
        "group": GROUP_ACTIVITY,
        "text": "Легко ли вам сейчас думать и понимать информацию?",
        "options": ("Очень трудно", "Трудно", "Не трудно и не легко",
                    "Легко", "Очень легко"),
    },
    {
        "id": "activity_focus",
        "group": GROUP_ACTIVITY,
        "text": "Легко ли вам сейчас сосредоточиться?",
        "options": ("Совсем не получается", "Трудно", "Не трудно и не легко",
                    "Легко", "Очень легко"),
    },
    {
        "id": "mood_general",
        "group": GROUP_MOOD,
        "text": "Как у вас настроение сейчас?",
        "options": ("Очень плохое", "Плохое", "Среднее", "Хорошее", "Отличное"),
    },
    {
        "id": "mood_calm",
        "group": GROUP_MOOD,
        "text": "Насколько спокойно вы себя сейчас чувствуете?",
        "options": ("Очень неспокойно", "Неспокойно", "Не совсем спокойно",
                    "Спокойно", "Совершенно спокойно"),
    },
)

QUESTION_IDS: tuple[str, ...] = tuple(item["id"] for item in QUESTIONS)
GROUPS: tuple[str, ...] = (GROUP_WELLBEING, GROUP_ACTIVITY, GROUP_MOOD)


def questionnaire() -> dict[str, Any]:
    """Опросник в виде, пригодном для показа.

    У каждого вопроса свои подписи к ответам; общая шкала возвращается рядом,
    чтобы пиктограммы выбирались по положению ответа.
    """
    return {
        "version": QUESTIONNAIRE_VERSION,
        "intro": INTRO,
        "scale": [dict(option) for option in SCALE],
        "questions": [
            {
                "id": item["id"],
                "group": item["group"],
                "text": item["text"],
                "options": [
                    {"value": SCALE[index]["value"], "label": label}
                    for index, label in enumerate(item["options"])
                ],
            }
            for item in QUESTIONS
        ],
    }


def score_san(answers: dict[str, Any]) -> dict[str, Any]:
    """Свести ответы по блокам.

    Пропущенный вопрос не заменяется средним: подставленное значение нельзя
    отличить от настоящего ответа, а опросник заполняется за полминуты.
    """
    values: dict[str, int] = {}
    for question_id in QUESTION_IDS:
        raw = answers.get(question_id)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        value = int(raw)
        if MIN_VALUE <= value <= MAX_VALUE:
            values[question_id] = value

    groups: list[dict[str, Any]] = []
    for group in GROUPS:
        ids = [item["id"] for item in QUESTIONS if item["group"] == group]
        answered = [values[item] for item in ids if item in values]
        groups.append({
            "group": group,
            "answered": len(answered),
            "question_count": len(ids),
            "score": sum(answered) if answered else None,
            "max_score": MAX_VALUE * len(ids),
            "mean": round(sum(answered) / len(answered), 2) if answered else None,
        })

    total = sum(values.values()) if values else None
    return {
        "version": QUESTIONNAIRE_VERSION,
        "answers": values,
        "groups": groups,
        "answered": len(values),
        "question_count": len(QUESTION_IDS),
        "complete": len(values) == len(QUESTION_IDS),
        "score": total,
        "max_score": MAX_VALUE * len(QUESTION_IDS),
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Изменение состояния за занятие.

    Сравниваются только блоки, заполненные с обеих сторон: разница с
    пропущенным ответом ничего не значит.
    """
    before_groups = {item["group"]: item for item in before.get("groups") or []}
    after_groups = {item["group"]: item for item in after.get("groups") or []}
    rows: list[dict[str, Any]] = []
    for group in GROUPS:
        start, end = before_groups.get(group), after_groups.get(group)
        if not start or not end or start.get("mean") is None or end.get("mean") is None:
            rows.append({"group": group, "change": None})
            continue
        rows.append({
            "group": group,
            "before": start["mean"],
            "after": end["mean"],
            "change": round(end["mean"] - start["mean"], 2),
        })
    return {"groups": rows}

# -*- coding: utf-8 -*-
"""Сверка шкалы HADS с бумажным ключом.

Ключ перенабран независимо из «Госпитальная Шкала Тревоги и Депрессии
(HADS).pdf». Экранный номер варианта (1–4) — только позиция кнопки;
балл берётся из HadsOption.score и обязан совпадать с PDF.
"""
from __future__ import annotations

import unittest

from neuro_mirror.screening.hads_scoring import (
    HADS_QUESTIONS,
    interpret_subscale,
    match_hads_answer,
    score_hads,
)

# [(текст варианта, балл), ...] в порядке появления в PDF
PDF_KEY: dict[str, list[tuple[str, int]]] = {
    # Часть I — ТРЕВОГА
    "anxiety_1": [
        ("всё время", 3), ("часто", 2),
        ("время от времени, иногда", 1), ("совсем не испытываю", 0),
    ],
    "anxiety_2": [
        ("определённо это так, и страх очень велик", 3),
        ("да, это так, но страх не очень велик", 2),
        ("иногда, но это меня не беспокоит", 1),
        ("совсем не испытываю", 0),
    ],
    "anxiety_3": [
        ("постоянно", 3), ("большую часть времени", 2),
        ("время от времени и не так часто", 1), ("только иногда", 0),
    ],
    "anxiety_4": [
        ("определённо, это так", 0), ("наверно, это так", 1),
        ("лишь изредка, это так", 2), ("совсем не могу", 3),
    ],
    "anxiety_5": [
        ("совсем не испытываю", 0), ("иногда", 1),
        ("часто", 2), ("очень часто", 3),
    ],
    "anxiety_6": [
        ("определённо, это так", 3), ("наверно, это так", 2),
        ("лишь в некоторой степени, это так", 1), ("совсем не испытываю", 0),
    ],
    "anxiety_7": [
        ("очень часто", 3), ("довольно часто", 2),
        ("не так уж часто", 1), ("совсем не бывает", 0),
    ],
    # Часть II — ДЕПРЕССИЯ
    "depression_1": [
        ("определённо, это так", 0), ("наверное, это так", 1),
        ("лишь в очень малой степени, это так", 2), ("это совсем не так", 3),
    ],
    "depression_2": [
        ("определённо, это так", 0), ("наверное, это так", 1),
        ("лишь в очень малой степени, это так", 2), ("совсем не способен", 3),
    ],
    "depression_3": [
        ("совсем не испытываю", 3), ("очень редко", 2),
        ("иногда", 1), ("практически всё время", 0),
    ],
    "depression_4": [
        ("практически всё время", 3), ("часто", 2),
        ("иногда", 1), ("совсем нет", 0),
    ],
    "depression_5": [
        ("определённо, это так", 3),
        ("я не уделяю этому столько времени, сколько нужно", 2),
        ("может быть, я стал меньше уделять этому времени", 1),
        ("я слежу за собой так же, как и раньше", 0),
    ],
    "depression_6": [
        ("точно так же, как и обычно", 0),
        ("да, но не в той степени, как раньше", 1),
        ("значительно меньше, чем обычно", 2),
        ("совсем так не считаю", 3),
    ],
    "depression_7": [
        ("часто", 0), ("иногда", 1), ("редко", 2), ("очень редко", 3),
    ],
}


class HadsPdfKeyTest(unittest.TestCase):
    def test_fourteen_questions_seven_per_subscale(self) -> None:
        self.assertEqual(len(HADS_QUESTIONS), 14)
        self.assertEqual(sum(1 for q in HADS_QUESTIONS if q.part == "anxiety"), 7)
        self.assertEqual(sum(1 for q in HADS_QUESTIONS if q.part == "depression"), 7)

    def test_every_option_matches_pdf_text_and_score(self) -> None:
        for question in HADS_QUESTIONS:
            pdf_options = PDF_KEY[question.question_id]
            self.assertEqual(len(question.options), 4, question.question_id)
            for position, (option, (pdf_text, pdf_score)) in enumerate(
                zip(question.options, pdf_options), start=1
            ):
                with self.subTest(question=question.question_id, position=position):
                    self.assertEqual(option.text, pdf_text)
                    self.assertEqual(option.score, pdf_score)

    def test_each_question_uses_scores_zero_to_three_once(self) -> None:
        for question in HADS_QUESTIONS:
            self.assertEqual(
                sorted(option.score for option in question.options),
                [0, 1, 2, 3],
                question.question_id,
            )


class HadsScoringTest(unittest.TestCase):
    def test_subscale_totals_and_interpretation(self) -> None:
        answers = []
        for question in HADS_QUESTIONS:
            target = 2 if question.part == "anxiety" else 1
            index = next(
                i for i, option in enumerate(question.options) if option.score == target
            )
            answers.append({
                "question_id": question.question_id,
                "part": question.part,
                "option_index": index,
                "option_text": question.options[index].text,
                "score": question.options[index].score,
            })

        result = score_hads(answers)
        self.assertEqual(result["anxiety_score"], 14)
        self.assertIn("клинически выраженная", result["anxiety_interpretation"])
        self.assertEqual(result["depression_score"], 7)
        self.assertIn("норма", result["depression_interpretation"])
        self.assertTrue(result["complete"])

    def test_interpretation_boundaries(self) -> None:
        self.assertEqual(interpret_subscale(0), "норма")
        self.assertEqual(interpret_subscale(7), "норма")
        self.assertEqual(interpret_subscale(8), "субклинически выраженная")
        self.assertEqual(interpret_subscale(10), "субклинически выраженная")
        self.assertEqual(interpret_subscale(11), "клинически выраженная")
        self.assertEqual(interpret_subscale(21), "клинически выраженная")

    def test_incomplete_run_is_flagged(self) -> None:
        result = score_hads([])
        self.assertFalse(result["complete"])
        self.assertTrue(result["notes"])


class HadsVoiceMatchTest(unittest.TestCase):
    def test_number_words_map_to_screen_positions(self) -> None:
        options = HADS_QUESTIONS[0].options
        self.assertEqual(match_hads_answer("один", options), 0)
        self.assertEqual(match_hads_answer("вариант два", options), 1)
        self.assertEqual(match_hads_answer("три", options), 2)
        self.assertEqual(match_hads_answer("четвёртый", options), 3)

    def test_option_text_matches_exactly(self) -> None:
        options = HADS_QUESTIONS[0].options
        self.assertEqual(match_hads_answer("совсем не испытываю", options), 3)
        self.assertEqual(match_hads_answer("часто", options), 1)

    def test_ambiguous_or_empty_input_is_rejected(self) -> None:
        options = HADS_QUESTIONS[0].options
        self.assertIsNone(match_hads_answer("два или три", options))
        self.assertIsNone(match_hads_answer("не понял", options))
        self.assertIsNone(match_hads_answer("", options))


if __name__ == "__main__":
    unittest.main()

"""Game matrix transcribed from the approved spreadsheet.

Only facts present in the matrix are represented here. Empty difficulty values
remain empty until the methodology defines them.
"""
from __future__ import annotations

from neuro_mirror.plugins.games.contracts import (
    DifficultyLevel,
    Domain,
    GameDefinition,
    Modality,
    ResponseType,
    normalise_game_code,
)

D = Domain
M = Modality
R = ResponseType


def _levels(*values: object, parameter: str) -> tuple[DifficultyLevel, ...]:
    return tuple(
        DifficultyLevel(index, {parameter: value})
        for index, value in enumerate(values, start=1)
        if value not in (None, "")
    )


GAME_CATALOG: tuple[GameDefinition, ...] = (
    GameDefinition("GM-01", "gm01_pair_cards", "Парные карточки", (D.MEMORY, D.ATTENTION),
                   ("memory_matching",), (M.VISUAL,), R.CLICK,
                   ("бытовые предметы", "животные", "фрукты и овощи"), "размер сетки",
                   _levels("5×2, два раза", "5×4", "6×4", parameter="grid"), ("M05", "U08"), ("M06", "U04", "U07", "U06")),
    GameDefinition("GM-02", "gm02_sequence", "Запомни последовательность", (D.MEMORY, D.ATTENTION),
                   ("spatial_sequence_recall",), (M.VISUAL,), R.CLICK, ("квадраты",), "количество циклов",
                   _levels(10, 15, 20, parameter="cycles"), ("M08", "M01"), ("M02", "M03", "U04", "U06")),
    GameDefinition("GM-03", "gm03_changed_object", "Что изменилось?", (D.MEMORY, D.ATTENTION),
                   ("object_location_recall",), (M.VISUAL,), R.CLICK, ("кухня", "ванная", "гостиная"),
                   "количество исчезнувших предметов", _levels(5, 7, 10, parameter="missing_items"),
                   ("U01",), ("M04", "U07", "U04", "U06")),
    GameDefinition("GM-04", "gm04_location", "Запомни расположение", (D.MEMORY, D.ATTENTION),
                   ("visual_pattern_recall",), (M.VISUAL,), R.CLICK, ("квадраты",), "размер матрицы и число целей",
                   _levels("4×4, 3–5", "8×8, 4–7", "10×10, 6–10", parameter="grid_and_targets"),
                   ("M07", "G08"), ("U03", "M04", "U04", "U06")),
    GameDefinition("GM-05", "gm05_word_list", "Список слов", (D.MEMORY, D.SPEECH),
                   ("word_recognition",), (M.VISUAL,), R.CLICK,
                   ("продукты питания", "одежда", "предметы быта"), "количество запоминаемых слов", (),
                   ("M07", "G08"), ("M10", "U04", "U06")),
    GameDefinition("GM-06", "gm06_rhythm", "Ритмическое повторение", (D.MEMORY, D.ATTENTION),
                   ("rhythm_reproduction", "sequence_recall"), (M.VISUAL, M.AUDITORY), R.CLICK,
                   ("нейтральные кнопки со звуком или подсветкой",), "количество циклов",
                   _levels(10, 15, 20, parameter="cycles"), ("M08", "M09"), ("M01", "M02", "M03", "U06")),
    GameDefinition("GM-07", "gm07_target_search", "Найди цель", (D.ATTENTION, D.MEMORY),
                   ("conjunction_visual_search",), (M.VISUAL,), R.CLICK,
                   ("буква Т", "треугольник", "число 3"), "количество объектов",
                   _levels(10, 15, 20, parameter="objects"), ("G07", "G08"), ("A01", "A02", "G03", "G05", "U06")),
    GameDefinition("GM-08", "gm08_stop_signal", "Стоп-сигнал", (D.ATTENTION, D.EXECUTIVE),
                   ("go_no_go", "response_inhibition"), (M.VISUAL,), R.CLICK,
                   ("буква В", "геометрические фигуры", "цифра 1"), "скорость предъявления", (),
                   ("G08", "G07"), ("G03", "G05", "U07", "U06")),
    GameDefinition("GM-09", "gm09_object_tracking", "Отслеживание объекта", (D.ATTENTION, D.MEMORY),
                   ("multiple_object_tracking",), (M.VISUAL,), R.CLICK,
                   ("треугольники", "воздушные шары", "силуэты птиц"), "число целей и скорость",
                   _levels(2, 3, 5, parameter="tracked_objects"), ("A06",), ("U03", "U04", "U06")),
    GameDefinition("GM-10", "gm10_find_difference", "Найди отличие", (D.ATTENTION,),
                   ("visual_comparison", "difference_search"), (M.VISUAL,), R.CLICK,
                   ("парк", "квартира", "магазин"), "количество отличий",
                   _levels(4, 6, 9, parameter="differences"), ("A07", "U07"), ("U04", "G06", "U06")),
    GameDefinition("GM-11", "gm11_serial_count", "Серийный счёт вслух", (D.ATTENTION, D.MEMORY, D.EXECUTIVE),
                   ("serial_arithmetic", "rule_switching"), (M.VISUAL, M.AUDITORY), R.SPOKEN,
                   ("вычитание", "сложение"), "частота смены операции", (), ("E08", "U07"), ("U04", "L08", "E07", "U06")),
    GameDefinition("GM-12", "gm12_word_picture", "Соедини слово и картинку", (D.SPEECH,),
                   ("word_picture_matching",), (M.VISUAL,), R.CLICK,
                   ("животные", "еда", "предметы быта"), "частота смены категории", (),
                   ("U01", "L01"), ("G03", "U07", "U06")),
    GameDefinition("GM-13", "gm13_categories", "Категории", (D.SPEECH, D.MEMORY, D.ATTENTION),
                   ("semantic_fluency",), (M.VISUAL, M.AUDITORY), R.SPOKEN,
                   ("овощи", "животные", "мебель"), "частота смены категории", (), ("L04",), ("L05", "L06", "L08", "L09", "U06")),
    GameDefinition("GM-14", "gm14_word_builder", "Собери слово", (D.SPEECH, D.ABSTRACTION, D.MEMORY),
                   ("anagram_solving", "word_assembly"), (M.VISUAL,), R.DRAG,
                   ("природа и явления", "еда и блюда", "одежда и бытовые приборы"), "длина слова",
                   _levels("3–4", "4–8", "6–12", parameter="letters"), ("U01",), ("L03", "U04", "G10", "U06")),
    GameDefinition("GM-15", "gm15_picture_naming", "Быстрое называние изображений", (D.SPEECH, D.MEMORY),
                   ("picture_naming",), (M.VISUAL, M.AUDITORY), R.SPOKEN,
                   ("животные", "предметы быта", "продукты питания"), "частота смены категории", (),
                   ("U01", "G03"), ("L01", "U07", "G07", "U06")),
    GameDefinition("GM-16", "gm16_phonemic_fluency", "Фонемная вербальная беглость", (D.SPEECH, D.ATTENTION, D.MEMORY, D.EXECUTIVE),
                   ("phonemic_fluency",), (M.VISUAL, M.AUDITORY), R.SPOKEN,
                   ("буквы с высокой частотностью слов",), "", (), ("L04",), ("L05", "L06", "L08", "L09", "U06")),
    GameDefinition("GM-17", "gm17_mental_rotation", "Поверни фигуру", (D.ABSTRACTION, D.ATTENTION, D.EXECUTIVE),
                   ("mental_rotation",), (M.VISUAL,), R.CLICK,
                   ("геометрические фигуры", "силуэты предметов", "силуэты животных"), "сложность и число вариантов",
                   _levels(2, 3, 4, parameter="choices"), ("U01",), ("G03", "U07", "U06")),
    GameDefinition("GM-18", "gm18_puzzle", "Пазлы", (D.ABSTRACTION, D.ATTENTION, D.EXECUTIVE),
                   ("jigsaw_assembly",), (M.VISUAL,), R.DRAG,
                   ("пейзаж", "натюрморт или интерьер", "портрет"), "количество фрагментов",
                   _levels(6, 12, 20, parameter="pieces"), ("U01", "U08"), ("E01", "U04", "G10", "U06")),
    GameDefinition("GM-19", "gm19_maze", "Лабиринт", (D.ABSTRACTION, D.ATTENTION, D.MEMORY, D.EXECUTIVE),
                   ("maze_tracing", "route_planning"), (M.VISUAL,), R.POINTER,
                   ("геометрический лабиринт",), "размер лабиринта", (), ("V02", "U08"), ("E03", "E04", "V03", "U06")),
    GameDefinition("GM-20", "gm20_rule_sorting", "Сортировка по правилу", (D.ABSTRACTION, D.ATTENTION, D.MEMORY, D.EXECUTIVE),
                   ("rule_sorting", "rule_switching"), (M.VISUAL,), R.CLICK,
                   ("цвет, форма и количество",), "частота смены правил", (), ("U01",), ("E06", "E07", "E05", "U06")),
    GameDefinition("GM-21", "gm21_odd_one_out", "Лишний предмет", (D.ABSTRACTION, D.MEMORY, D.ATTENTION, D.EXECUTIVE),
                   ("odd_one_out", "categorisation"), (M.VISUAL,), R.CLICK,
                   ("животные", "продукты", "инструменты"), "смена категорий и очевидность признака", (),
                   ("U01",), ("G03", "U07", "U06")),
    GameDefinition("GM-22", "gm22_tower", "Башня / перестановка фигур", (D.ABSTRACTION, D.MEMORY, D.ATTENTION, D.EXECUTIVE),
                   ("tower_planning",), (M.VISUAL,), R.CLICK, ("цветные диски",), "количество элементов",
                   _levels(3, 5, 7, parameter="elements"), ("U03", "E05"), ("E01", "E03", "E04", "U07", "U06")),
    GameDefinition("GM-23", "gm23_matrix_reasoning", "Продолжи закономерность", (D.ABSTRACTION, D.ATTENTION, D.EXECUTIVE),
                   ("matrix_reasoning", "pattern_completion"), (M.VISUAL,), R.CLICK,
                   ("звезда", "треугольник", "сердце"), "количество схожих вариантов", (),
                   ("U01",), ("G03", "U07", "U06")),
    GameDefinition("GM-24", "gm24_category_naming", "Категориальное называние", (D.ABSTRACTION, D.SPEECH, D.MEMORY, D.EXECUTIVE),
                   ("verbal_abstraction", "categorisation"), (M.VISUAL, M.AUDITORY), R.SPOKEN,
                   ("животные", "фрукты", "овощи", "транспорт", "мебель", "инструменты", "одежда"),
                   "частота смены категории", (), ("U01",), ("G03", "L01", "U07", "U06")),
)

_BY_CODE = {item.code: item for item in GAME_CATALOG}
_BY_SLUG = {item.slug: item for item in GAME_CATALOG}


def get_game_definition(code_or_slug: str) -> GameDefinition:
    definition = _BY_SLUG.get(code_or_slug)
    if definition is None:
        definition = _BY_CODE.get(normalise_game_code(code_or_slug))
    if definition is None:
        raise KeyError(f"Неизвестный код игры: {code_or_slug}")
    return definition

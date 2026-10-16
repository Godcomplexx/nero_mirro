"""Puzzle scenes and layouts for GM-18."""


PUZZLES_BY_LEVEL = {
    1: (
        {"name": "Парк", "image": "park_a.png"},
        {"name": "Кухня", "image": "kitchen_easy_01_a.png"},
        {"name": "Детская площадка", "image": "playground_easy_02_a.png"},
        {"name": "Спальня", "image": "bedroom_easy_03_a.png"},
        {"name": "Сад", "image": "garden_easy_04_a.png"},
    ),
    2: (
        {"name": "Комната", "image": "apartment_a.png"},
        {"name": "Кафе", "image": "cafe_medium_01_a.png"},
        {"name": "Учебный класс", "image": "classroom_medium_02_a.png"},
        {"name": "Библиотека", "image": "library_medium_03_a.png"},
    ),
    3: (
        {"name": "Магазин", "image": "shop_a.png"},
        {"name": "Станция", "image": "station_hard_01_a.png"},
        {"name": "Мастерская", "image": "workshop_hard_02_a.png"},
    ),
}

BONUS_PUZZLE = {"name": "Дополнительный пазл", "image": "park_a.png", "rows": 3, "columns": 4}

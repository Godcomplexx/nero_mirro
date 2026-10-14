"""Image pairs and normalized answer regions for GM-10."""

STIMULUS_SET_VERSION = "4"

SCENES_BY_LEVEL = {
    1: (
        {"name": "Парк", "left": "park_a.png", "right": "park_b.png", "radius": .065,
         "differences": ((.38,.40),(.57,.66),(.88,.54),(.18,.80))},
        {"name": "Кухня", "left": "kitchen_easy_01_a.png", "right": "kitchen_easy_01_b.png", "radius": .075,
         "differences": ((.10,.30),(.75,.31),(.53,.58),(.86,.28))},
        {"name": "Детская площадка", "left": "playground_easy_02_a.png", "right": "playground_easy_02_b.png", "radius": .075,
         "differences": ((.67,.14),(.39,.56),(.68,.83),(.62,.59),(.31,.42),(.82,.55))},
        {"name": "Спальня", "left": "bedroom_easy_03_a.png", "right": "bedroom_easy_03_b.png", "radius": .075,
         "differences": ((.29,.12),(.08,.34),(.39,.34),(.14,.61))},
        {"name": "Сад", "left": "garden_easy_04_a.png", "right": "garden_easy_04_b.png", "radius": .075,
         "differences": ((.47,.27),(.43,.79),(.23,.57),(.75,.18))},
    ),
    2: (
        {"name": "Квартира", "left": "apartment_a.png", "right": "apartment_b.png", "radius": .075,
         "differences": ((.45,.20),(.57,.50),(.33,.48),(.73,.86),(.72,.13),(.56,.68))},
        {"name": "Кафе", "left": "cafe_medium_01_a.png", "right": "cafe_medium_01_b.png", "radius": .08,
         "differences": ((.23,.32),(.27,.66),(.55,.55),(.62,.20),(.92,.08),(.88,.36))},
        {"name": "Класс", "left": "classroom_medium_02_a.png", "right": "classroom_medium_02_b.png", "radius": .08,
         "differences": ((.62,.22),(.80,.08),(.34,.70),(.80,.72),(.35,.22),(.44,.42),(.25,.31))},
        {"name": "Библиотека", "left": "library_medium_03_a.png", "right": "library_medium_03_b.png", "radius": .08,
         "differences": ((.30,.57),(.78,.42),(.64,.27),(.70,.65),(.56,.28),(.70,.44))},
    ),
    3: (
        {"name": "Магазин", "left": "shop_a.png", "right": "shop_b.png", "radius": .08,
         "differences": ((.76,.08),(.76,.29),(.30,.12),(.15,.58),(.47,.67),(.90,.84),(.95,.48),(.10,.43),(.94,.20))},
        {"name": "Станция", "left": "station_hard_01_a.png", "right": "station_hard_01_b.png", "radius": .075,
         "differences": ((.20,.12),(.67,.13),(.81,.51),(.16,.70),(.36,.74),(.34,.25),(.47,.42),(.29,.54),(.39,.56))},
        {"name": "Мастерская", "left": "workshop_hard_02_a.png", "right": "workshop_hard_02_b.png", "radius": .075,
         "differences": ((.25,.65),(.52,.42),(.66,.47),(.79,.49),(.88,.34),(.49,.72),(.81,.16),(.76,.39),(.85,.80))},
    ),
}

SCENES = tuple(scene for level_scenes in SCENES_BY_LEVEL.values() for scene in level_scenes)

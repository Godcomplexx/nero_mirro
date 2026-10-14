"""Picture sets and timing for GM-15.

GM-12 and GM-15 use the same object library. Keeping the file/name mapping
in one place prevents new pictures from remaining unavailable for naming.
"""
from __future__ import annotations

from neuro_mirror.plugins.games.gm12_word_picture.stimuli import ITEMS


RECORDING_MS = 3_500

ALIASES = {
    "собака": ("пёс", "пес"),
    "медведь": ("мишка",),
    "лиса": ("лисица",),
    "обезьяна": ("мартышка",),
    "мышь": ("мышка",),
    "кролик": ("заяц",),
    "часы": ("будильник",),
    "расчёска": ("расческа", "гребень"),
    "чашка": ("кружка",),
    "лампа": ("светильник",),
    "зонт": ("зонтик",),
    "хлеб": ("батон",),
    "морковь": ("морковка",),
    "клубника": ("земляника",),
    "помидор": ("томат",),
    "картофель": ("картошка",),
}

CATEGORY_NAMES = {
    "животные": "Животные",
    "предметы быта": "Предметы быта",
    "еда": "Продукты питания",
}

PICTURE_SETS = tuple(
    (
        display_name,
        tuple(
            {
                "name": word.capitalize(),
                "file": file_name,
                "answers": (word, *ALIASES.get(word, ())),
            }
            for category, word, file_name in ITEMS
            if category == source_name
        ),
    )
    for source_name, display_name in CATEGORY_NAMES.items()
)

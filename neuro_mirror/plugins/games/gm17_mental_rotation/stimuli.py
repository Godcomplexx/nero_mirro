STIMULUS_SET_VERSION = "4"
TRIAL_COUNT = 30
SHAPES: dict[str, list[list[int]]] = {
    "step": [[18, 18], [58, 18], [58, 38], [82, 38], [82, 82], [42, 82], [42, 62], [18, 62]],
    "flag": [[18, 12], [78, 12], [60, 35], [78, 58], [34, 58], [34, 88], [18, 88]],
    "hook": [[18, 16], [50, 16], [50, 58], [82, 58], [82, 84], [18, 84]],
    "arrow": [[15, 38], [55, 38], [55, 18], [86, 50], [55, 82], [55, 62], [15, 62]],
    "kite": [[50, 12], [84, 44], [66, 86], [28, 72], [16, 34]],
    "zig": [[18, 14], [72, 14], [54, 43], [84, 43], [30, 88], [44, 56], [16, 56]],
    "boot": [[18, 14], [46, 14], [46, 58], [76, 58], [88, 82], [18, 82]],
    "chair": [[18, 14], [44, 14], [44, 48], [80, 48], [80, 84], [58, 84], [58, 66], [18, 66]],
    "notch": [[14, 16], [86, 16], [86, 42], [62, 42], [62, 84], [36, 84], [36, 58], [14, 58]],
    "castle": [[14, 20], [34, 20], [34, 38], [50, 38], [50, 16], [70, 16], [70, 38], [86, 38], [86, 82], [14, 82]],
    "key": [[14, 36], [36, 36], [36, 16], [60, 16], [60, 38], [86, 38], [86, 62], [58, 62], [58, 84], [34, 84], [34, 62], [14, 62]],
    "fork": [[16, 16], [38, 16], [38, 38], [52, 38], [52, 16], [76, 16], [76, 56], [58, 56], [58, 86], [34, 86], [34, 58], [16, 58]],
}


def _polyomino(cells: tuple[tuple[int, int], ...]) -> list[list[int]]:
    """Convert joined unit squares into one scaled SVG polygon outline."""
    occupied = set(cells)
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for x, y in occupied:
        if (x, y - 1) not in occupied:
            edges.append(((x, y), (x + 1, y)))
        if (x + 1, y) not in occupied:
            edges.append(((x + 1, y), (x + 1, y + 1)))
        if (x, y + 1) not in occupied:
            edges.append(((x + 1, y + 1), (x, y + 1)))
        if (x - 1, y) not in occupied:
            edges.append(((x, y + 1), (x, y)))

    next_point = {start: end for start, end in edges}
    start = min(next_point, key=lambda point: (point[1], point[0]))
    outline = [start]
    current = next_point[start]
    while current != start:
        outline.append(current)
        current = next_point[current]

    min_x = min(x for x, _ in outline)
    max_x = max(x for x, _ in outline)
    min_y = min(y for _, y in outline)
    max_y = max(y for _, y in outline)
    scale = 68 / max(max_x - min_x, max_y - min_y)
    offset_x = 50 - ((max_x + min_x) * scale / 2)
    offset_y = 50 - ((max_y + min_y) * scale / 2)
    return [
        [round(offset_x + x * scale), round(offset_y + y * scale)]
        for x, y in outline
    ]


SHAPES.update(
    {
        "pent_f": _polyomino(((1, 0), (2, 0), (0, 1), (1, 1), (1, 2))),
        "pent_i": _polyomino(((0, 0), (0, 1), (0, 2), (0, 3), (0, 4))),
        "pent_l": _polyomino(((0, 0), (0, 1), (0, 2), (0, 3), (1, 3))),
        "pent_p": _polyomino(((0, 0), (1, 0), (0, 1), (1, 1), (0, 2))),
        "pent_n": _polyomino(((0, 0), (0, 1), (1, 1), (1, 2), (1, 3))),
        "pent_t": _polyomino(((0, 0), (1, 0), (2, 0), (1, 1), (1, 2))),
        "pent_u": _polyomino(((0, 0), (2, 0), (0, 1), (1, 1), (2, 1))),
        "pent_v": _polyomino(((0, 0), (0, 1), (0, 2), (1, 2), (2, 2))),
        "pent_w": _polyomino(((0, 0), (0, 1), (1, 1), (1, 2), (2, 2))),
        "pent_x": _polyomino(((1, 0), (0, 1), (1, 1), (2, 1), (1, 2))),
        "pent_y": _polyomino(((0, 0), (0, 1), (1, 1), (0, 2), (0, 3))),
        "pent_z": _polyomino(((0, 0), (1, 0), (1, 1), (1, 2), (2, 2))),
        "long_branch": _polyomino(((0, 0), (1, 0), (2, 0), (3, 0), (1, 1), (1, 2))),
        "corner_tail": _polyomino(((0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 3))),
        "double_step": _polyomino(((0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2))),
        "wide_hook": _polyomino(((0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (1, 2))),
        "offset_cross": _polyomino(((1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (1, 3))),
        "split_stem": _polyomino(((0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2))),
    }
)

IMAGE_SHAPES = {
    "object:book": "book.png", "object:clock": "clock.png",
    "object:comb": "comb.png", "object:cup": "cup.png",
    "object:kettle": "kettle.png", "object:key": "key.png",
    "object:lamp": "lamp.png", "object:pencil": "pencil.png",
    "object:scissors": "scissors.png", "object:umbrella": "umbrella.png",
    "animal:bear": "bear.png", "animal:cat": "cat.png",
    "animal:dog": "dog.png", "animal:fox": "fox.png",
    "animal:frog": "frog.png", "animal:lion": "lion.png",
    "animal:monkey": "monkey.png", "animal:mouse": "mouse.png",
    "animal:panda": "panda.png", "animal:rabbit": "rabbit.png",
}

SHAPE_SETS = {
    "геометрические фигуры": ("step", "flag", "hook", "arrow", "kite", "zig", "boot", "chair", "notch", "castle", "key", "fork"),
    "силуэты предметов": tuple(key for key in IMAGE_SHAPES if key.startswith("object:")),
    "силуэты животных": tuple(key for key in IMAGE_SHAPES if key.startswith("animal:")),
}


def shape_payload(key: str) -> dict[str, object]:
    return {"image": IMAGE_SHAPES[key]} if key in IMAGE_SHAPES else {"points": SHAPES[key]}

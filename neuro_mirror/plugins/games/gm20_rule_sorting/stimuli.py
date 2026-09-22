STIMULUS_SET_VERSION = "1"
TRIAL_COUNT = 60
RULES = ("color", "shape", "count")
COLORS = ("red", "green", "blue", "yellow")
SHAPES = ("triangle", "circle", "square", "star")
REFERENCES = tuple(
    {"id": f"reference-{index}", "color": COLORS[index], "shape": SHAPES[index], "count": index + 1}
    for index in range(4)
)

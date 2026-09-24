"""Image pairs and normalized answer regions for GM-10."""

STIMULUS_SET_VERSION = "1"
SCENES = (
    {"name": "Парк", "left": "park_a.png", "right": "park_b.png", "radius": .065,
     "differences": ((.38,.40),(.57,.66),(.88,.54),(.18,.80))},
    {"name": "Квартира", "left": "apartment_a.png", "right": "apartment_b.png", "radius": .075,
     "differences": ((.45,.20),(.57,.50),(.33,.48),(.73,.86),(.72,.13),(.56,.68))},
    {"name": "Магазин", "left": "shop_a.png", "right": "shop_b.png", "radius": .08,
     "differences": ((.76,.08),(.76,.29),(.30,.12),(.15,.58),(.47,.67),(.90,.84),(.95,.48),(.10,.43),(.94,.20))},
)

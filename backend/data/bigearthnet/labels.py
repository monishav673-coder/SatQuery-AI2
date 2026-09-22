"""
SATQUERY AI — BigEarthNet Label Definitions
19-class and 43-class nomenclature from the BigEarthNet dataset.
Reference: https://bigearth.net/
"""

# ── 19-class nomenclature (recommended for classification tasks) ──────────────
BEN_19_CLASSES = [
    "Urban fabric",
    "Industrial or commercial units",
    "Arable land",
    "Permanent crops",
    "Pastures",
    "Complex cultivation patterns",
    "Land principally occupied by agriculture, with significant areas of natural vegetation",
    "Agro-forestry areas",
    "Broad-leaved forest",
    "Coniferous forest",
    "Mixed forest",
    "Natural grassland and sparsely vegetated areas",
    "Moors, heathland, and sclerophyllous vegetation",
    "Transitional woodland/shrub",
    "Beaches, dunes, sands",
    "Inland wetlands",
    "Coastal wetlands",
    "Inland waters",
    "Marine waters",
]

# ── 43-class nomenclature (full CORINE Land Cover level-3 subset) ─────────────
BEN_43_CLASSES = [
    "Continuous urban fabric",
    "Discontinuous urban fabric",
    "Industrial or commercial units",
    "Road and rail networks and associated land",
    "Port areas",
    "Airports",
    "Mineral extraction sites",
    "Dump sites",
    "Construction sites",
    "Green urban areas",
    "Sport and leisure facilities",
    "Non-irrigated arable land",
    "Permanently irrigated land",
    "Rice fields",
    "Vineyards",
    "Fruit trees and berry plantations",
    "Olive groves",
    "Pastures",
    "Annual crops associated with permanent crops",
    "Complex cultivation patterns",
    "Land principally occupied by agriculture, with significant areas of natural vegetation",
    "Agro-forestry areas",
    "Broad-leaved forest",
    "Coniferous forest",
    "Mixed forest",
    "Natural grassland",
    "Moors and heathland",
    "Sclerophyllous vegetation",
    "Transitional woodland/shrub",
    "Beaches, dunes, sands",
    "Bare rock",
    "Sparsely vegetated areas",
    "Burnt areas",
    "Inland marshes",
    "Peatbogs",
    "Salt marshes",
    "Salines",
    "Intertidal flats",
    "Water courses",
    "Water bodies",
    "Coastal lagoons",
    "Estuaries",
    "Sea and ocean",
]

# ── Mapping BigEarthNet → SATQUERY display classes ────────────────────────────
# Groups BEN classes into the 7 high-level display classes used in the UI.
BEN_TO_DISPLAY = {
    "Water": [
        "Inland waters", "Marine waters", "Water courses", "Water bodies",
        "Coastal lagoons", "Estuaries", "Sea and ocean", "Intertidal flats",
    ],
    "Agriculture / Cropland": [
        "Arable land", "Permanent crops", "Pastures",
        "Complex cultivation patterns",
        "Land principally occupied by agriculture, with significant areas of natural vegetation",
        "Agro-forestry areas",
        "Non-irrigated arable land", "Permanently irrigated land", "Rice fields",
        "Vineyards", "Fruit trees and berry plantations", "Olive groves",
        "Annual crops associated with permanent crops",
    ],
    "Forest / Vegetation": [
        "Broad-leaved forest", "Coniferous forest", "Mixed forest",
        "Natural grassland and sparsely vegetated areas",
        "Moors, heathland, and sclerophyllous vegetation",
        "Transitional woodland/shrub", "Natural grassland",
        "Moors and heathland", "Sclerophyllous vegetation",
    ],
    "Built-up / Urban": [
        "Urban fabric",
        "Industrial or commercial units",
        "Continuous urban fabric", "Discontinuous urban fabric",
        "Road and rail networks and associated land", "Port areas", "Airports",
        "Mineral extraction sites", "Construction sites",
        "Green urban areas", "Sport and leisure facilities",
    ],
    "Bare Land": [
        "Beaches, dunes, sands", "Bare rock", "Sparsely vegetated areas",
        "Burnt areas", "Dump sites",
    ],
    "Wetlands": [
        "Inland wetlands", "Coastal wetlands",
        "Inland marshes", "Peatbogs", "Salt marshes", "Salines",
    ],
    "Other": [],
}


def get_display_class(ben_label: str) -> str:
    """Map a BigEarthNet label to a SATQUERY display class."""
    for display, ben_labels in BEN_TO_DISPLAY.items():
        if ben_label in ben_labels:
            return display
    return "Other"


def labels_to_display_classes(ben_labels: list) -> list:
    """
    Convert a list of BigEarthNet multi-labels to SATQUERY display class dicts.
    Each entry: {label, source_labels, confidence, note}
    """
    display_map: dict = {}
    for lbl in ben_labels:
        display = get_display_class(lbl)
        if display not in display_map:
            display_map[display] = []
        display_map[display].append(lbl)

    return [
        {
            "label": display,
            "source_labels": srcs,
            "percentage": None,
            "area_km2": None,
            "confidence": 75.0,
            "direction": "N/A",
            "note": "Derived from BigEarthNet reference classification.",
        }
        for display, srcs in display_map.items()
    ]

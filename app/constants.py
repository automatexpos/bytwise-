"""
Python equivalents of the shared vibe/parking constants in constants.ts.

INITIAL_SHOPS and PAKISTANI_FAKE_NAMES are intentionally left out here
since they are not part of this task's scope (no default/demo shops, and
fake names are only used by seed scripts), but the four constants called
out in the task are reproduced exactly.
"""

from typing import Dict, List

STANDARD_VIBES: Dict[str, List[str]] = {
    "atmosphere": [
        "Cozy",
        "Quiet",
        "Aesthetic",
        "Outdoor Seating",
    ],
    "foodDrink": [
        "Chai",
        "Coffee",
        "Specialty Coffee",
        "Desi Food",
        "Desserts",
    ],
    "purpose": [
        "Laptop Friendly",
        "Study Spot",
        "Date Spot",
        "Family Friendly",
    ],
    "facilities": [
        "Fast WiFi",
        "Air Conditioned",
        "Easy Parking",
        "Clean Washrooms",
    ],
}

CHEEKY_VIBES_OPTIONS: Dict[str, List[str]] = {
    "social": [
        "Gup Shup",
        "Girls Night",
        "Family Hangout",
        "Boys Night",
        "Hidden Gem",
        "Worth The Hype",
    ],
    "money": [
        "Pocket Friendly",
        "Paisay Wasool",
        "A Little Pricey",
        "Worth The Splurge",
    ],
    "workStudy": [
        "WFC, Work From Cafe",
        "Freelancer Friendly",
        "Study Mode",
        "Deadline Spot",
        "Coffee & Code",
    ],
    "pakistaniEnergy": [
        "Parents Approved",
        "Chai Ka Bahana",
        "Bas 10 Minute Aur",
        "Diet Kal Se",
        "Late Night Cravings",
        "Long Drive Worthy",
    ],
}

# Object.values(STANDARD_VIBES).flat() from constants.ts
STANDARD_VIBE_OPTIONS: List[str] = [
    vibe for group in STANDARD_VIBES.values() for vibe in group
]

PARKING_OPTIONS: List[str] = [
    "Dedicated Parking",
    "Street Parking",
    "Valet Parking",
    "Nearby Parking",
    "Difficult Parking",
    "No Parking",
    "Unknown",
]

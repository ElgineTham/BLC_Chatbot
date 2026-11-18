"""The beverage pull sheet items the tool can be about (spec 007 section 3.1)."""

from __future__ import annotations

import re

PULL_SHEET_ITEMS: dict[str, tuple[str, ...]] = {
    "gallons": ("gallon", "gallons", "gal"),
    "cambros": ("cambro", "cambros", "jug", "jugs", "container", "containers"),
    "cups": ("cup", "cups"),
    "napkins": ("napkin", "napkins"),
    "creamer": ("creamer",),
    "stir sticks": ("stir stick", "stir sticks"),
    "sugar": ("sugar",),
    "lemon tongs": ("lemon tongs", "tongs"),
    "lemons": ("lemon", "lemons"),
    "tea packets": ("tea packet", "tea packets", "tea bag", "tea bags"),
    "everything": ("bring", "pull sheet", "pack"),
}  # canonical item name -> the words that mean it (all lower case)


def _word_pattern(word: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in word.split())
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)


_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    item: tuple(_word_pattern(word) for word in words)
    for item, words in PULL_SHEET_ITEMS.items()
}


def pull_sheet_items_in(text: str) -> tuple[str, ...]:
    """Canonical names of the items whose words appear in text, each at most once, in the
    order of PULL_SHEET_ITEMS. Whole words or phrases only, ignoring case."""
    if not isinstance(text, str) or not text.strip():
        return ()
    return tuple(
        item
        for item, patterns in _PATTERNS.items()
        if any(pattern.search(text) for pattern in patterns)
    )

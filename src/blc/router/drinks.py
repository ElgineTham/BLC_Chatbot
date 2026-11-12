"""The menu drink names the router must not lose (spec 010 section 3.1)."""

from __future__ import annotations

import re

MENU_DRINKS: tuple[str, ...] = (
    "coffee", "decaf", "hot water", "brewed hot cider", "ginger honeycrisp apple cider",
    "cider", "iced water", "iced tea", "orange juice", "lemonade", "peach tea", "oatmilk",
    "tea", "juice", "package",
)  # lower case words and phrases that name a menu drink or the package


def _pattern(name: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in name.split())
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, _pattern(name)) for name in MENU_DRINKS
)


def menu_drinks_in(text: str) -> tuple[str, ...]:
    """The entries of MENU_DRINKS that appear in text, each at most once, in MENU_DRINKS
    order. Whole words or phrases, ignoring case. () for no match or blank text."""
    if not isinstance(text, str) or not text.strip():
        return ()
    return tuple(name for name, pattern in _PATTERNS if pattern.search(text))

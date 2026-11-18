"""Checking and cleaning the item, guests and meal values (spec 029 4.4)."""

from __future__ import annotations

import math

from blc.tools.food_tools.result import FOOD_ITEMS
from blc.tools.food_tools.rules import meal_key

_SINGULARS = {
    "spoon": "spoons", "fork": "forks", "knife": "knives",
    "small plate": "small plates", "large plate": "large plates",
    "cocktail napkin": "cocktail napkins", "dinner napkin": "dinner napkins",
}
_ITEM_KEYS = {**{name: name for name in FOOD_ITEMS}, **_SINGULARS}


class BadValue(Exception):
    """A value that makes the call invalid; the message says what was wrong."""


def _single_string(value: object, label: str) -> str | None:
    """A string, or a list of exactly one string; None when missing or null."""
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise BadValue(f'"{label}" must be one value, not {len(value)}')
        value = value[0]
    if value is None:
        return None
    if not isinstance(value, str):
        raise BadValue(f'"{label}" must be text')
    return value


def check_item(value: object) -> str:
    """The canonical item name. Raises BadValue."""
    text = _single_string(value, "item")
    key = " ".join((text or "").casefold().replace("_", " ").replace("-", " ").split())
    if not key:
        raise BadValue('"item" is missing or blank')
    if key not in _ITEM_KEYS:
        raise BadValue(f'unknown "item" {text!r}')
    return _ITEM_KEYS[key]


def _whole_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip()) if "." in value else int(value.strip())
        except ValueError:
            return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value == int(value):
        return int(value)
    return None


def check_guests(value: object) -> int | None:
    """A whole number >= 1, or None when not given (null or 0). Raises BadValue."""
    if value is None:
        return None
    number = _whole_number(value)
    if number is None or number < 0:
        raise BadValue(f'"guests" must be a whole number of 1 or more, not {value!r}')
    return number or None


def check_meal(value: object, meals: tuple[str, ...]) -> str | None:
    """The canonical meal, or None when not given. Raises BadValue."""
    text = _single_string(value, "meal")
    if text is None or not text.strip():
        return None
    key = meal_key(text)
    if key not in meals:
        raise BadValue(f'unknown "meal" {text!r}')
    return key

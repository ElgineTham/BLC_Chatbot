"""The text the tool returns to the chat model (spec 015 4.6). No I/O."""

from __future__ import annotations

import math
from fractions import Fraction

FORMAT_HELP = (
    'Expected format: {"recipe": "<drink name>", "gallons": <number above 0>} or '
    '{"recipe": "<drink name>", "guests": <whole number>}. '
    'Example calls: {"recipe": "iced tea", "gallons": 2} or '
    '{"recipe": "iced tea", "guests": 40}.'
)


def number_text(value: Fraction) -> str:
    """Whole numbers without decimals, else at most two decimals, trailing zeros dropped."""
    hundredths = math.floor(value * 100 + Fraction(1, 2))
    whole, part = divmod(hundredths, 100)
    if part == 0:
        return str(whole)
    return f"{whole}.{part:02d}".rstrip("0")


def gallons_text(value: Fraction) -> str:
    return f"{number_text(value)} {'gallon' if value == 1 else 'gallons'}"


def ingredient_line(name: str, amount: Fraction, unit: str, fill: bool) -> str:
    if fill:
        return f"{name}: fill to {gallons_text(amount)}"
    return f"{name}: {number_text(amount)} {unit}"


def ok_text(
    recipe: str, gallons: Fraction, guests: int | None, lines: list[str], steps: tuple[str, ...]
) -> str:
    source = f" (from {guests} guests)" if guests is not None else ""
    numbered = " ".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    header = f"{recipe} for {gallons_text(gallons)}{source}:"
    return "\n".join([header, *lines, f"Steps: {numbered}"])


def need_info_text(recipe: str) -> str:
    return f"How many gallons of {recipe} do you want to make, or how many guests are you serving?"


def no_recipe_text(requested: str, names: tuple[str, ...]) -> str:
    return f"There is no recipe named {requested.strip()}. Recipes available: {', '.join(names)}."


def invalid_text(reason: str) -> str:
    return f"invalid: {reason}. {FORMAT_HELP}"

"""The tool's text for the chat model (spec 042 4.5); no I/O."""

from __future__ import annotations

EXAMPLE_CALL = (
    '{"items": [{"food": "butter croissants", "qty": 3, "unit": "dozen"}, '
    '{"food": "classic deli sandwiches", "qty": 50}]}'
)
NO_UTENSILS_TEXT = "These foods need no serving utensils."
READING_LABEL = "Counted for:"
_READING_DECIMALS = 2


def format_amount(number: float) -> str:
    """Whole numbers without a decimal; others with up to 2 decimals."""
    rounded = round(number, _READING_DECIMALS)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{_READING_DECIMALS}f}".rstrip("0")


def reading_line(readings: list[tuple[str, float, str]]) -> str:
    parts = "; ".join(f"{food} {format_amount(qty)} {unit}" for food, qty, unit in readings)
    return f"{READING_LABEL} {parts}"


def ok_text(utensils: dict[str, int], readings: list[tuple[str, float, str]] | None = None) -> str:
    body = (
        "\n".join(f"{name.capitalize()}: {total}" for name, total in utensils.items())
        if utensils else NO_UTENSILS_TEXT
    )
    return f"{body}\n{reading_line(readings)}" if readings else body


def need_info_text(foods: list[str]) -> str:
    return f"How many {' and '.join(foods)} are ordered?"


def invalid_text(problems: list[str], has_unknown_food: bool = False) -> str:
    hint = ' Use the name of a food from the menu as "food".' if has_unknown_food else ""
    return (
        f"Invalid call: {'; '.join(problems)}.{hint} Expected format: "
        '{"items": [{"food": <food name>, "qty": <number>, "unit": <optional unit>}]}. '
        f"Example: {EXAMPLE_CALL}"
    )

"""The text the food tool gives the chat model (spec 029 4.6)."""

from __future__ import annotations

from blc.tools.food_tools.result import COUNT_ITEMS, FOOD_ITEMS

EXAMPLE_CALLS = (
    '{"item": "forks", "guests": 70} or {"item": "dinner napkins", "meal": "lunch"}'
)


def ok_count_text(item: str, guests: int, extra: int, count: int) -> str:
    return f"{item.capitalize()}: {count} ({guests} guests + {extra} extra)"


def ok_napkin_text(item: str, meal: str, answer: bool) -> str:
    return f"{item.capitalize()} for {meal}: {'yes' if answer else 'no'}"


def need_info_text(item: str, meals: tuple[str, ...]) -> str:
    if item in COUNT_ITEMS:
        return f"How many guests are there for the {item}?"
    return f"Which meal is it (one of {', '.join(meals)})?"


def invalid_text(problem: str, show_items: bool) -> str:
    text = (
        f"invalid: {problem}. Expected format: "
        '{"item": <item>, "guests": <whole number, for count items>, '
        '"meal": <meal, for napkin items>}. '
        f"Example calls: {EXAMPLE_CALLS}."
    )
    if show_items:
        text += f" The item must be one of: {', '.join(FOOD_ITEMS)}."
    return text

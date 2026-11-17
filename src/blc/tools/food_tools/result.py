"""The names, statuses and result type of the food tool (spec 029 3.1)."""

from __future__ import annotations

from dataclasses import dataclass

FOOD_TOOL_NAME = "calculate_food_item"
FOOD_ITEMS: tuple[str, ...] = (
    "spoons", "forks", "knives", "small plates", "large plates",
    "cocktail napkins", "dinner napkins",
)
FOOD_STATUSES: tuple[str, ...] = ("ok", "need_info", "invalid")
COUNT_ITEMS: tuple[str, ...] = FOOD_ITEMS[:5]
NAPKIN_ITEMS: tuple[str, ...] = FOOD_ITEMS[5:]


@dataclass(frozen=True)
class FoodResult:
    status: str  # one of FOOD_STATUSES
    text: str  # what the tool returns to the chat model
    item: str | None = None
    guests: int | None = None
    extra: int | None = None
    count: int | None = None
    answer: bool | None = None
    meal: str | None = None

"""Which domain (food, beverage, napkin, other) a knowledge file belongs to."""

from __future__ import annotations

from pathlib import PurePosixPath

FOOD = "food"
BEVERAGE = "beverage"
NAPKIN = "napkin"
DOMAINS: tuple[str, ...] = (FOOD, BEVERAGE, NAPKIN)
OTHER_DOMAIN = "other"

FOOD_SOURCES = frozenset({"data/pull_sheet/menu/food.md"})
NAPKIN_SOURCES = frozenset({"data/pull_sheet/rules/napkins.md"})
BEVERAGE_SOURCES = frozenset(
    {"data/pull_sheet/menu/beverages.md", "data/pull_sheet/rules/beverages.md"}
)
BEVERAGE_DIRS = ("data/supplies", "data/recipes")


def domain_for(source: str) -> str:
    """source is a path from the project root, e.g. 'data/pull_sheet/menu/food.md'."""
    path = PurePosixPath(source.replace("\\", "/"))
    text = path.as_posix()
    if text in FOOD_SOURCES:
        return FOOD
    if text in NAPKIN_SOURCES:
        return NAPKIN
    if text in BEVERAGE_SOURCES:
        return BEVERAGE
    if path.suffix == ".md" and path.parent.as_posix() in BEVERAGE_DIRS:
        return BEVERAGE
    return OTHER_DOMAIN

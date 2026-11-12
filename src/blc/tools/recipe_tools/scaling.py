"""Scaling a recipe to a batch size (spec 015 4.2 to 4.4). Pure calculation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from blc.pull_sheet.text import guests_to_gallons
from blc.tools.recipe_tools.book import Recipe, RecipeBook, load_recipe_book
from blc.tools.recipe_tools.reply_text import (
    ingredient_line,
    invalid_text,
    need_info_text,
    no_recipe_text,
    ok_text,
)

RECIPE_STATUSES: tuple[str, ...] = ("ok", "need_info", "no_recipe", "invalid")
FILL_UNIT = "gallon"


@dataclass(frozen=True)
class ScaledIngredient:
    name: str
    amount: Fraction
    unit: str
    fill: bool


@dataclass(frozen=True)
class RecipeResult:
    status: str
    text: str
    recipe: str | None
    gallons: Fraction | None
    from_guests: bool
    ingredients: tuple[ScaledIngredient, ...]
    steps: tuple[str, ...]


def invalid_result(reason: str) -> RecipeResult:
    return RecipeResult("invalid", invalid_text(reason), None, None, False, (), ())


def _gallons_value(gallons: object) -> Fraction | None:
    """The gallons as an exact Fraction, or None when not a number above 0."""
    if isinstance(gallons, bool) or not isinstance(gallons, (int, float, Fraction)):
        return None
    if isinstance(gallons, float):
        if not math.isfinite(gallons):
            return None
        gallons = Fraction(str(gallons))
    value = Fraction(gallons)
    return value if value > 0 else None


def _check_inputs(recipe: object, gallons: object, guests: object) -> str | None:
    if not isinstance(recipe, str) or not recipe.strip():
        return "recipe must be the name of a drink"
    if gallons is not None and _gallons_value(gallons) is None:
        return "gallons must be a number above 0"
    if guests is not None and (
        isinstance(guests, bool) or not isinstance(guests, int) or guests < 1
    ):
        return "guests must be a whole number of 1 or more"
    return None


def _scale_one(item_amount: Fraction | None, batch: Fraction, yield_gallons: Fraction) -> Fraction:
    return batch if item_amount is None else item_amount * batch / yield_gallons


def _scaled(recipe: Recipe, batch: Fraction, guests: int | None) -> RecipeResult:
    scaled = tuple(
        ScaledIngredient(
            item.name,
            _scale_one(item.amount, batch, recipe.yield_gallons),
            FILL_UNIT if item.fill else str(item.unit),
            item.fill,
        )
        for item in recipe.ingredients
    )
    lines = [ingredient_line(i.name, i.amount, i.unit, i.fill) for i in scaled]
    text = ok_text(recipe.name, batch, guests, lines, recipe.steps)
    return RecipeResult("ok", text, recipe.name, batch, guests is not None, scaled, recipe.steps)


def scale_recipe(
    recipe: str,
    gallons: int | float | Fraction | None = None,
    guests: int | None = None,
    book: RecipeBook | None = None,
) -> RecipeResult:
    """Pure calculation. book=None means load_recipe_book(). Never raises for bad user
    input (status "invalid"). RecipeFileError from loading the book propagates."""
    reason = _check_inputs(recipe, gallons, guests)
    if reason:
        return invalid_result(reason)
    book = book if book is not None else load_recipe_book()
    found = book.find(recipe)
    if found is None:
        text = no_recipe_text(recipe, book.names())
        return RecipeResult("no_recipe", text, None, None, False, (), ())
    if gallons is not None:
        return _scaled(found, _gallons_value(gallons), None)  # type: ignore[arg-type]
    if guests is not None:
        return _scaled(found, guests_to_gallons(guests), guests)
    return RecipeResult("need_info", need_info_text(found.name), found.name, None, False, (), ())

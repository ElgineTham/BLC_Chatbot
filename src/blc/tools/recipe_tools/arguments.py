"""Reading the raw arguments the chat model sends (spec 015 4.5). No I/O."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from fractions import Fraction

from blc.tools.recipe_tools.book import RecipeBook
from blc.tools.recipe_tools.scaling import RecipeResult, invalid_result, scale_recipe

RECIPE_FALLBACK_KEYS: tuple[str, ...] = ("drink", "drinks", "name")
_DECIMAL = re.compile(r"\d+(?:\.\d+)?|\.\d+", re.ASCII)


class _BadArgument(Exception):
    """A raw argument is not usable; the message says what was wrong."""


def _string_or_single(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        return value[0]
    return None


def _recipe_name(args: Mapping[str, object]) -> str:
    value = args.get("recipe")
    missing = value is None or (isinstance(value, str) and not value.strip()) or value == []
    if not missing:
        name = _string_or_single(value)
        if name is None:
            raise _BadArgument("recipe must be one drink name")
        return name
    for key in RECIPE_FALLBACK_KEYS:
        name = _string_or_single(args.get(key))
        if name is not None:
            return name
    raise _BadArgument("recipe must be one drink name")


def _number(value: object) -> Fraction | None:
    """A number or numeric text as an exact Fraction; None if it is neither."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Fraction)):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(str(value)) if math.isfinite(value) else None
    if isinstance(value, str) and _DECIMAL.fullmatch(value.strip()):
        return Fraction(value.strip())
    return None


def _gallons(value: object) -> Fraction | None:
    if isinstance(value, list):
        if not value:
            return None
        if len(value) > 1:
            raise _BadArgument("gallons must be one number")
        value = value[0]
    if value is None:
        return None
    number = _number(value)
    if number is None:
        raise _BadArgument("gallons must be a number above 0")
    if number == 0:
        return None
    if number < 0:
        raise _BadArgument("gallons must be a number above 0")
    return number


def _guests(value: object) -> int | None:
    if value is None:
        return None
    number = _number(value)
    if number is None or number < 0 or number.denominator != 1:
        raise _BadArgument("guests must be a whole number of 1 or more")
    return int(number) or None


def run_recipe_tool(args: Mapping[str, object], book: RecipeBook | None = None) -> RecipeResult:
    """Run the tool on a raw argument dict as the chat model sends it. Never raises for
    bad arguments: they give status "invalid"."""
    if not isinstance(args, Mapping):
        return invalid_result("the arguments must be an object")
    try:
        recipe = _recipe_name(args)
        gallons = _gallons(args.get("gallons"))
        guests = _guests(args.get("guests"))
    except _BadArgument as error:
        return invalid_result(str(error))
    return scale_recipe(recipe, gallons, guests, book)

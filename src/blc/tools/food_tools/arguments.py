"""Running the food tool on the raw argument dict from the chat model (spec 029 4.4)."""

from __future__ import annotations

from collections.abc import Mapping

from blc.tools.food_tools.calculator import calculate_food_item
from blc.tools.food_tools.reply_text import invalid_text
from blc.tools.food_tools.result import FoodResult
from blc.tools.food_tools.rules import FoodRules


def run_food_tool(args: Mapping[str, object], rules: FoodRules | None = None) -> FoodResult:
    """Never raises for bad arguments: they give status "invalid"."""
    if not isinstance(args, Mapping):
        return FoodResult("invalid", invalid_text("the arguments must be an object", True))
    return calculate_food_item(
        args.get("item"), args.get("guests"), args.get("meal"), rules  # type: ignore[arg-type]
    )

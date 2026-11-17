"""Food supplies tool for the chat model (spec 029).

The calculations load no LangChain; FOOD_TOOL and make_food_tool load it when first used.
"""

from __future__ import annotations

from typing import Any

from blc.tools.food_tools.arguments import run_food_tool
from blc.tools.food_tools.calculator import calculate_food_item
from blc.tools.food_tools.result import (
    FOOD_ITEMS,
    FOOD_STATUSES,
    FOOD_TOOL_NAME,
    FoodResult,
)
from blc.tools.food_tools.rules import (
    FOOD_RULES_FILE,
    FoodRules,
    FoodRulesError,
    load_food_rules,
)

__all__ = [
    "FOOD_TOOL_NAME", "FOOD_ITEMS", "FOOD_STATUSES", "FOOD_RULES_FILE", "FoodRulesError",
    "FoodRules", "load_food_rules", "FoodResult", "calculate_food_item", "run_food_tool",
    "make_food_tool", "FOOD_TOOL",
]
_LAZY = ("FOOD_TOOL", "make_food_tool")


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from blc.tools.food_tools import tool

        return getattr(tool, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

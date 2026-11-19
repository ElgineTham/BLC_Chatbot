"""Recipe scaling tool for the chat model (spec 015).

The calculations load no LangChain; RECIPE_TOOL and make_recipe_tool load it when first used.
"""

from __future__ import annotations

from typing import Any

from blc.tools.recipe_tools.arguments import run_recipe_tool
from blc.tools.recipe_tools.bags import BAG_UNIT
from blc.tools.recipe_tools.book import (
    RECIPES_FILE,
    RecipeBook,
    RecipeFileError,
    load_recipe_book,
)
from blc.tools.recipe_tools.scaling import (
    RECIPE_TOOL_NAME,
    RECIPE_STATUSES,
    RecipeResult,
    ScaledIngredient,
    scale_recipe,
)

__all__ = [
    "BAG_UNIT",
    "RECIPE_TOOL_NAME", "RECIPE_STATUSES", "RECIPES_FILE", "RecipeFileError", "RecipeBook",
    "load_recipe_book", "ScaledIngredient", "RecipeResult", "scale_recipe",
    "run_recipe_tool", "make_recipe_tool", "RECIPE_TOOL",
]
_LAZY = ("RECIPE_TOOL", "make_recipe_tool")


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from blc.tools.recipe_tools import tool

        return getattr(tool, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

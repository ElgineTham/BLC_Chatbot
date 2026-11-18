"""Beverage calculator tool for the chat model (spec 005).

The calculations load no LangChain; BEV_TOOL and make_bev_tool load it when first used.
"""

from __future__ import annotations

from typing import Any

from blc.tools.bev_tools.arguments import run_bev_tool
from blc.tools.bev_tools.calculator import (
    BEV_ITEMS,
    BEV_STATUSES,
    BEV_TOOL_NAME,
    BevResult,
    calculate_bev_item,
)
from blc.tools.bev_tools.catalog import Catalog, load_catalog
from blc.tools.bev_tools.catalog_entries import EACH, GALLON
from blc.tools.bev_tools.drinks import DrinkAmount, DrinkRequest
from blc.tools.bev_tools.gallons import GUESTS_PER_GALLON, guests_to_gallons
from blc.tools.bev_tools.json_checks import RuleFileError
from blc.tools.bev_tools.pull_line import PullLine

__all__ = [
    "BEV_TOOL_NAME", "BEV_ITEMS", "BEV_STATUSES", "DrinkRequest", "DrinkAmount",
    "BevResult", "calculate_bev_item", "run_bev_tool", "make_bev_tool", "BEV_TOOL",
    "Catalog", "load_catalog", "RuleFileError", "PullLine", "GALLON", "EACH",
    "GUESTS_PER_GALLON", "guests_to_gallons",
]
_LAZY = ("BEV_TOOL", "make_bev_tool")


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from blc.tools.bev_tools import tool

        return getattr(tool, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

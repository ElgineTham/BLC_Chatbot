"""BEV_TOOL: the LangChain tool the chat model calls (flat schema, spec 005 section 3.3)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.pull_sheet import Catalog
from blc.tools.bev_tools.arguments import run_bev_tool
from blc.tools.bev_tools.calculator import BEV_ITEMS

BEV_TOOL_NAME = "calculate_bev_item"
BEV_TOOL_DESCRIPTION = (
    "Calculates beverage pull sheet amounts exactly: gallons, cambros, cups or supplies "
    "for the drinks and guest count the user gave. You must use this tool instead of "
    "calculating these numbers yourself. If the result asks a question, ask the user "
    "that question. Example calls: "
    '{"item": "cambros", "drinks": ["brewed hot cider", "peach tea"], "gallons": [6, 4]} '
    'and {"item": "supplies", "drinks": ["decaf"], "guests": 45} '
    'and {"item": "cups", "guests": 30}.'
)
ITEM_DESCRIPTION = (
    "What the user wants to know. gallons: how many gallons to make. cambros: which "
    "cambros or containers to use, or what to put or serve a drink in. cups: how many "
    "cups are needed. supplies: whether to bring a particular supply (sugar, creamer, "
    "napkins and so on). everything: what to bring in general."
)
DRINKS_DESCRIPTION = (
    "Names of the drinks the user mentioned, as they said them (case does not matter): "
    "Coffee, Decaf, Hot water, Brewed hot cider, Ginger Honeycrisp apple cider, Iced water, "
    "Iced tea, Orange juice, Lemonade, Peach tea, Oatmilk. The package "
    '"Coffee, decaf, tea, iced water & juice" is passed as one name. '
    "Leave this out when no drink was named."
)
GALLONS_DESCRIPTION = (
    "Amounts of the drinks, in the same order as drinks. The numbers are gallons, except "
    "Oatmilk, whose number is a count of pieces. One number for several drinks applies "
    "to each. Leave this out when no amounts were given. Use only amounts the user said, "
    "never amounts you worked out from the number of guests."
)
GUESTS_DESCRIPTION = (
    "Number of guests or people. Leave this out when no guest or people count was given."
)

BEV_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "item": {"type": "string", "enum": list(BEV_ITEMS), "description": ITEM_DESCRIPTION},
        "drinks": {
            "type": "array", "items": {"type": "string"}, "description": DRINKS_DESCRIPTION,
        },
        "gallons": {
            "type": "array",
            "items": {"type": "number", "exclusiveMinimum": 0},
            "description": GALLONS_DESCRIPTION,
        },
        "guests": {"type": "integer", "minimum": 1, "description": GUESTS_DESCRIPTION},
    },
    "required": ["item"],
}


class BevTool(BaseTool):
    """Passes the raw arguments to run_bev_tool so bad input gives "invalid", not an error."""

    name: str = BEV_TOOL_NAME
    description: str = BEV_TOOL_DESCRIPTION
    args_schema: dict[str, Any] | None = BEV_SCHEMA
    catalog: Catalog | None = None

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return run_bev_tool(kwargs, self.catalog).text


def make_bev_tool(catalog: Catalog | None = None) -> BaseTool:
    """The chat tool; catalog=None loads the real files when the tool runs."""
    return BevTool(catalog=catalog)


BEV_TOOL: BaseTool = make_bev_tool()

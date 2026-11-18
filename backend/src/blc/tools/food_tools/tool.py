"""FOOD_TOOL: the LangChain tool the chat model calls (flat schema, spec 029 3.2)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.food_tools.arguments import run_food_tool
from blc.tools.food_tools.result import FOOD_TOOL_NAME
from blc.tools.food_tools.rules import FoodRules

FOOD_TOOL_DESCRIPTION = (
    "Works out how many spoons, forks, knives, small plates or large plates to bring for a "
    "number of guests (a count), and whether an event needs cocktail napkins or dinner "
    "napkins for a meal type (yes or no). You must use this tool instead of calculating "
    "yourself. If the result asks a question, ask the user that question. Example calls: "
    '{"item": "forks", "guests": 70} and {"item": "dinner napkins", "meal": "lunch"}.'
)
ITEM_DESCRIPTION = (
    "One of: spoons, forks, knives, small plates, large plates, cocktail napkins, "
    "dinner napkins."
)
GUESTS_DESCRIPTION = (
    "The guest count the user said. Leave this out when no guest count was given."
)
MEAL_DESCRIPTION = (
    "The meal type: breakfast, reception, lunch or dinner. Only for napkin items."
)

FOOD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "item": {"type": "string", "description": ITEM_DESCRIPTION},
        "guests": {"type": "integer", "minimum": 1, "description": GUESTS_DESCRIPTION},
        "meal": {"type": "string", "description": MEAL_DESCRIPTION},
    },
    "required": ["item"],
}


class FoodTool(BaseTool):
    """Passes the raw arguments to run_food_tool so bad input gives "invalid", not an error."""

    name: str = FOOD_TOOL_NAME
    description: str = FOOD_TOOL_DESCRIPTION
    args_schema: dict[str, Any] | None = FOOD_SCHEMA
    rules: FoodRules | None = None

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return run_food_tool(kwargs, self.rules).text


def make_food_tool(rules: FoodRules | None = None) -> BaseTool:
    """The chat tool; rules=None loads the real file when the tool runs."""
    return FoodTool(rules=rules)


FOOD_TOOL: BaseTool = make_food_tool()

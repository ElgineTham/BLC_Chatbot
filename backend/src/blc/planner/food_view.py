"""PLANNER_FOOD_TOOL: the planner's own view of calculate_food_item (spec 030)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.food_tools.result import FOOD_TOOL_NAME

PLANNER_FOOD_DESCRIPTION = (
    "Works out exactly how many spoons, forks, knives, small plates or large plates to bring "
    "for a guest count the user gave, and whether an event needs cocktail napkins or dinner "
    "napkins for a meal type (breakfast, reception, lunch or dinner). Do not use it for cups, "
    "gallons, cambros or napkins asked about with a drink. Don't invent a guest count. "
    "Example calls: "
    '{"item": "spoons", "guests": 110} '
    'and {"item": "cocktail napkins", "meal": "dinner"}.'
)
PLANNER_FOOD_ITEM_DESCRIPTION = (
    "What to work out: spoons, forks, knives, small plates, large plates, cocktail napkins "
    "or dinner napkins."
)
PLANNER_FOOD_GUESTS_DESCRIPTION = (
    "The guest count the user said, as a number. For the count items only. Leave this out "
    "when no guest count was given in the question or the chat history."
)
PLANNER_FOOD_MEAL_DESCRIPTION = (
    "The meal type: breakfast, reception, lunch or dinner. For the napkin items only."
)


def _planner_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": PLANNER_FOOD_ITEM_DESCRIPTION},
            "guests": {"type": "integer", "description": PLANNER_FOOD_GUESTS_DESCRIPTION},
            "meal": {"type": "string", "description": PLANNER_FOOD_MEAL_DESCRIPTION},
        },
        "required": ["item"],
    }


class PlannerFoodTool(BaseTool):
    """Schema-only view: the planner never runs it."""

    name: str = FOOD_TOOL_NAME
    description: str = PLANNER_FOOD_DESCRIPTION
    args_schema: dict[str, Any] | None = _planner_schema()

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return ""


PLANNER_FOOD_TOOL: BaseTool = PlannerFoodTool()

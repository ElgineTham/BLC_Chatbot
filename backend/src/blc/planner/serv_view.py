"""PLANNER_SERV_TOOL: the planner's own view of calculate_serving_utensils (spec 043)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.serv_tools.result import SERV_TOOL_NAME

PLANNER_SERV_DESCRIPTION = (
    "Works out exactly which serving utensils to pull (small tongs, large tongs, salad tongs, "
    "serving spoons, spreaders or knives, honey bears, ladles, sauce bowls) and how many, for "
    "foods with amounts, or for the food lines of a BEO. Put every food line in one call. "
    "Do not use it for forks, spoons, knives, plates or napkins by guest count, nor for cups, "
    "gallons or cambros. Don't invent an amount. "
    "Example calls: "
    '{"items": [{"food": "scones", "qty": 5, "unit": "dozen"}, '
    '{"food": "classic deli sandwiches", "qty": 20, "unit": "each"}]} '
    'and, for a breakfast package of 45 people whose item lines read "Butter croissants 45": '
    '{"items": [{"food": "butter croissants", "qty": 45, "unit": "each"}, '
    '{"food": "freshly cut fruit platter", "qty": 45, "unit": "each"}]} '
    'and, for 2 medium fruit trays: {"items": [{"food": "medium market fresh fruit tray", '
    '"qty": 2, "unit": "each"}]}. '
    "A fruit tray ordered on its own is a small, medium or large market fresh fruit tray, "
    "counted in trays. \"freshly cut fruit platter\" is only the fruit line of a breakfast package. "
    "Units: a plain count before a food with no unit word (a number of sandwiches) counts pieces, "
    'so send "unit": "each". Send "dozen" only when the user writes dozen or a BEO line\'s unit is '
    "dozen. Leave the unit out only when no amount was given."
)
PLANNER_SERV_ITEMS_DESCRIPTION = (
    "One entry per food line, in order. The package line itself (for example the name of a "
    "breakfast package) may be left out; send the foods inside it instead."
)
PLANNER_SERV_FOOD_DESCRIPTION = "The name of the food, as the user or the BEO wrote it."
PLANNER_SERV_QTY_DESCRIPTION = (
    "The amount exactly as the user or BEO wrote it, never converted by you. Leave this out "
    "when no amount was given in the question or the chat history."
)
PLANNER_SERV_UNIT_DESCRIPTION = (
    "The unit exactly as written (each, dozen, bags, packages); leave it out when none was "
    "written. A plain count with no unit word is \"each\"; \"dozen\" only when written. The item "
    "lines of a package are a number of people, so they use \"each\"."
)


def _planner_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": PLANNER_SERV_ITEMS_DESCRIPTION,
                "items": {
                    "type": "object",
                    "properties": {
                        "food": {"type": "string", "description": PLANNER_SERV_FOOD_DESCRIPTION},
                        "qty": {"type": "number", "description": PLANNER_SERV_QTY_DESCRIPTION},
                        "unit": {"type": "string", "description": PLANNER_SERV_UNIT_DESCRIPTION},
                    },
                    "required": ["food"],
                },
            },
        },
        "required": ["items"],
    }


class PlannerServTool(BaseTool):
    """Schema-only view: the planner never runs it."""

    name: str = SERV_TOOL_NAME
    description: str = PLANNER_SERV_DESCRIPTION
    args_schema: dict[str, Any] | None = _planner_schema()

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return ""


PLANNER_SERV_TOOL: BaseTool = PlannerServTool()

"""PLANNER_BEV_TOOL: the planner's own view of calculate_bev_item (spec 018; deleted in spec 019)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.bev_tools.tool import BEV_SCHEMA, BEV_TOOL_NAME, DRINKS_DESCRIPTION, GUESTS_DESCRIPTION

NO_INVENTED_RULE = "Don't invent arguments or numbers that aren't there!"
PLANNER_BEV_ITEMS: tuple[str, ...] = ("gallons", "cambros", "cups", "everything")
PLANNER_BEV_DESCRIPTION = (
    "Calculates beverage amounts exactly from an amount the user gave: how many gallons of a "
    "drink to make, which cambros, how many cups, or the full pull sheet for drinks with an "
    "amount. How much of an ingredient a batch needs is scale_recipe's job, not this tool's. "
    + NO_INVENTED_RULE
    + " Example calls: "
    '{"item": "cambros", "drinks": ["brewed hot cider", "peach tea"], "gallons": [6, 4]} '
    'and {"item": "cups", "guests": 30} '
    'and {"item": "everything", "drinks": ["iced water"], "gallons": [10]}.'
)
PLANNER_ITEM_DESCRIPTION = (
    "What to work out. gallons: how many gallons of a drink to make. cambros: which cambros "
    "or containers to use. cups: how many cups. everything: the full pull sheet for drinks "
    "with an amount. How much of an ingredient a batch needs is scale_recipe's job."
)
PLANNER_GALLONS_DESCRIPTION = (
    "Amounts of the drinks, in the same order as drinks. The numbers are gallons, except "
    "Oatmilk, whose number is a count of pieces. One number for several drinks applies "
    "to each. Leave this out when no amounts were given. Use only amounts the user said, "
    "never amounts you worked out from the number of guests."
)


def _planner_schema() -> dict[str, Any]:
    properties = {key: dict(value) for key, value in BEV_SCHEMA["properties"].items()}
    properties["item"] = {
        "type": "string", "enum": list(PLANNER_BEV_ITEMS), "description": PLANNER_ITEM_DESCRIPTION,
    }
    properties["drinks"]["description"] = DRINKS_DESCRIPTION
    properties["gallons"]["description"] = PLANNER_GALLONS_DESCRIPTION
    properties["guests"]["description"] = GUESTS_DESCRIPTION
    return {"type": "object", "properties": properties, "required": ["item"]}


class PlannerBevTool(BaseTool):
    """Schema-only view: the planner never runs it."""

    name: str = BEV_TOOL_NAME
    description: str = PLANNER_BEV_DESCRIPTION
    args_schema: dict[str, Any] | None = _planner_schema()

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return ""


PLANNER_BEV_TOOL: BaseTool = PlannerBevTool()

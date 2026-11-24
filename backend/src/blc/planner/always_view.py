"""PLANNER_ALWAYS_TOOL: the planner's own view of calculate_always_items (spec 045)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.always_tools import ALWAYS_TOOL_NAME

PLANNER_ALWAYS_DESCRIPTION = (
    "Use for any question about black linens, purple napkins, black napkins, or the Always "
    "items, the Always box or a pull sheet, with or without a number. "
    "Choose about in this order, first match wins: "
    "1) the question names the Always items, the Always box or a pull sheet: \"both\", even "
    "when it gives only one count; "
    "2) else black linens, purple napkins, or only tables: \"tables\"; "
    "3) else black napkins, or only drip trays: \"drip_trays\"; "
    "4) else (names neither): \"both\". "
    "Leave out any number the user did not write in the question or chat history, and never "
    "guess 1 or 0; the tool then asks for it. Bus tubs and towels always come and need no "
    "number. Not for forks, spoons, knives, plates or cocktail or dinner napkins by guest "
    "count. "
    "Examples: "
    '"Black linens for 9 tables?" -> {"about": "tables", "tables": 9}; '
    '"How many black napkins should I pull?" -> {"about": "drip_trays"}; '
    '"Always items for 7 drip trays?" -> {"about": "both", "drip_trays": 7}.'
)
PLANNER_ALWAYS_ABOUT_DESCRIPTION = (
    "First match wins: \"both\" if the question names the Always items, the Always box or a "
    "pull sheet (even with one count); else \"tables\" for black linens, purple napkins or "
    "only tables; else \"drip_trays\" for black napkins or only drip trays; else \"both\"."
)
PLANNER_ALWAYS_TABLES_DESCRIPTION = (
    "The number of tables exactly as the user or BEO wrote it (not a table size such as 6-ft, "
    "and not a guest count). Leave it out when it was not given in the question or chat "
    "history; never guess 1 or 0."
)
PLANNER_ALWAYS_DRIP_TRAYS_DESCRIPTION = (
    "The number of drip trays exactly as the user or BEO wrote it. Leave it out when it was "
    "not given in the question or chat history; never guess 1 or 0."
)


def _planner_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "about": {"type": "string", "description": PLANNER_ALWAYS_ABOUT_DESCRIPTION},
            "tables": {"type": "integer", "description": PLANNER_ALWAYS_TABLES_DESCRIPTION},
            "drip_trays": {"type": "integer", "description": PLANNER_ALWAYS_DRIP_TRAYS_DESCRIPTION},
        },
        "required": ["about"],
    }


class PlannerAlwaysTool(BaseTool):
    """Schema-only view: the planner never runs it."""

    name: str = ALWAYS_TOOL_NAME
    description: str = PLANNER_ALWAYS_DESCRIPTION
    args_schema: dict[str, Any] | None = _planner_schema()

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return ""


PLANNER_ALWAYS_TOOL: BaseTool = PlannerAlwaysTool()

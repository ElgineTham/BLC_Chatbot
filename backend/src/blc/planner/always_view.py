"""PLANNER_ALWAYS_TOOL: the planner's own view of calculate_always_items (spec 045)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.always_tools import ALWAYS_TOOL_NAME

PLANNER_ALWAYS_DESCRIPTION = (
    "Use for any question about linens, tablecloths, black linens, white linens, purple napkins, black napkins, or the Always "
    "items, the Always box or a pull sheet, with or without a number. "
    "Choose about in this order, first match wins: "
    "1) the question names the Always items, the Always box or a pull sheet: \"both\", even "
    "when it gives only one count; "
    "2) else linens, tablecloths, black or white linens, purple napkins, or only tables: \"tables\"; "
    "3) else black napkins, or only drip trays: \"drip_trays\"; "
    "4) else (names neither): \"both\". "
    "Leave out any number the user did not write in the question or chat history, and never "
    "guess 1 or 0; the tool then asks for it. Bus tubs and towels always come and need no "
    "number. Not for forks, spoons, knives, plates or cocktail or dinner napkins by guest "
    "count. "
    "Linens or tablecloths with no colour are black linens: \"tables\" is the number of tables "
    "with black linens, and \"white_tables\" the number with white linens, sent only when the "
    "user says white. Questions about white linens use about \"tables\" (or \"both\" by the "
    "rules above). "
    "Examples: "
    '"Black linens for 41 tables?" -> {"about": "tables", "tables": 41}; '
    '"White linens for 53 tables?" -> {"about": "tables", "white_tables": 53}; '
    '"How many black napkins should I pull?" -> {"about": "drip_trays"}; '
    '"Always items for 37 drip trays?" -> {"about": "both", "drip_trays": 37}.'
)
PLANNER_ALWAYS_ABOUT_DESCRIPTION = (
    "First match wins: \"both\" if the question names the Always items, the Always box or a "
    "pull sheet (even with one count); else \"tables\" for black linens, purple napkins or "
    "only tables; else \"drip_trays\" for black napkins or only drip trays; else \"both\"."
)
PLANNER_ALWAYS_TABLES_DESCRIPTION = (
    "The number of tables with black linens (linens, tablecloths or a table count with no colour are black), exactly as the user or BEO wrote it (not a table size such as 6-ft, "
    "and not a guest count). Leave it out when it was not given in the question or chat "
    "history; never guess 1 or 0."
)
PLANNER_ALWAYS_WHITE_TABLES_DESCRIPTION = (
    "The number of tables with white linens, exactly as the user or BEO wrote it. Send it only "
    "when the user says white. Leave it out when it was not given in the question or chat "
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
            "white_tables": {"type": "integer", "description": PLANNER_ALWAYS_WHITE_TABLES_DESCRIPTION},
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

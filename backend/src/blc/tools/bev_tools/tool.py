"""Schema text of the beverage tool (spec 005 section 3.3); the planner builds its view from it."""

from __future__ import annotations

from typing import Any

from blc.tools.bev_tools.calculator import BEV_ITEMS, BEV_TOOL_NAME

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


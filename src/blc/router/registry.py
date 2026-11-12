"""The tool lookup table, choosing a tool for a part, and the classifier prompt (spec 013 4.4)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from blc.router.items import PULL_SHEET_ITEMS

RECIPE_TOOL = "scale_recipe"
BEV_TOOL_NAME = "calculate_bev_item"

CLASSIFIER_TEMPLATE = (
    "Label each numbered line. Reply with one letter per line, like TD.\n"
    "T = a number, or a yes/no about what to bring, worked out by a tool:\n"
    "{tools}\n"
    "Use T for: how many cambros, cups or gallons; which cambros hold N gallons; "
    "whether to bring a supply (sugar, creamer, napkins); what to bring or what goes "
    "on the pull sheet.\n"
    "D = a lookup in the documents: where things are, what something is, flavors, "
    "cleaning, schedules, how something is made or done. A number that does not change "
    "the answer is still D.\n"
    "Examples:\n"
    "Which cambros hold 12 gallons of hot water? T\n"
    "Do I need napkins for the cider? T\n"
    "What goes on the pull sheet for decaf for 80 people? T\n"
    "Where is the tea kept? D\n"
    "What does \"iced tea with lemon wedges\" mean? D\n"
    "Letters only."
)


@dataclass(frozen=True)
class ToolEntry:
    name: str                    # the tool's name as the chat model sees it
    purpose: str                 # one line: what the tool does
    keywords: tuple[str, ...]    # lower case words or phrases that point at this tool
    available: bool              # False: not built yet; the router never picks it


def _all_item_words() -> tuple[str, ...]:
    return tuple(word for words in PULL_SHEET_ITEMS.values() for word in words)


TOOL_REGISTRY: tuple[ToolEntry, ...] = (
    ToolEntry(
        RECIPE_TOOL,
        "Scales a recipe's ingredient amounts to a number of gallons or guests.",
        ("recipe", "ingredient", "ingredients", "concentrate", "oz", "ounce", "ounces",
         "how to make", "how do i make", "how do we make", "how can i make"),
        False,
    ),
    ToolEntry(
        BEV_TOOL_NAME,
        "Calculates beverage pull sheet amounts (gallons, cambros, cups, supplies) "
        "for drinks and guest counts.",
        _all_item_words(),
        True,
    ),
)


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        body = r"\s+".join(re.escape(part) for part in keyword.split())
        if re.search(rf"(?<![a-z0-9]){body}(?![a-z0-9])", text, re.IGNORECASE):
            return True
    return False


def pick_tool(text: str, registry: tuple[ToolEntry, ...] = TOOL_REGISTRY) -> str | None:
    """Name of the tool for text: the first entry in table order whose keywords match,
    if it is available; None if it is not (no fall through). Never raises."""
    if not isinstance(text, str) or not text.strip():
        return None
    for entry in registry:
        if _has_keyword(text, entry.keywords):
            return entry.name if entry.available else None
    return None


def classifier_prompt(registry: tuple[ToolEntry, ...] = TOOL_REGISTRY) -> str:
    """The system prompt for the one-letter-per-part classifier, built from the table."""
    tools = "\n".join(f"- {entry.purpose}" for entry in registry if entry.available)
    return CLASSIFIER_TEMPLATE.format(tools=tools)

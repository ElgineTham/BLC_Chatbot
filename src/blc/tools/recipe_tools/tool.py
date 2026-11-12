"""RECIPE_TOOL: the LangChain tool the chat model calls (flat schema, spec 015 3.3)."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from blc.tools.recipe_tools.arguments import run_recipe_tool
from blc.tools.recipe_tools.book import RecipeBook

RECIPE_TOOL_NAME = "scale_recipe"
RECIPE_TOOL_DESCRIPTION = (
    "Scales a recipe's ingredient amounts to a batch size and gives the method steps. "
    "You must use this tool instead of calculating the amounts yourself. If the result "
    "asks a question, ask the user that question. Example calls: "
    '{"recipe": "lemonade", "gallons": 2} and {"recipe": "fresh lemonade", "guests": 40}.'
)
RECIPE_DESCRIPTION = "The name of the drink or recipe, as the user said it."
GALLONS_DESCRIPTION = (
    "The batch size in gallons that the user said. Leave this out when no gallons were "
    "given. Never work it out from the number of guests."
)
GUESTS_DESCRIPTION = (
    "Number of guests or people. Leave this out when no guest or people count was given."
)

RECIPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recipe": {"type": "string", "description": RECIPE_DESCRIPTION},
        "gallons": {"type": "number", "exclusiveMinimum": 0, "description": GALLONS_DESCRIPTION},
        "guests": {"type": "integer", "minimum": 1, "description": GUESTS_DESCRIPTION},
    },
    "required": ["recipe"],
}


class RecipeTool(BaseTool):
    """Passes the raw arguments to run_recipe_tool so bad input gives "invalid", not an error."""

    name: str = RECIPE_TOOL_NAME
    description: str = RECIPE_TOOL_DESCRIPTION
    args_schema: dict[str, Any] | None = RECIPE_SCHEMA
    book: RecipeBook | None = None

    def _parse_input(self, tool_input: Any, tool_call_id: str | None = None) -> Any:
        return tool_input

    def _run(self, **kwargs: Any) -> str:
        return run_recipe_tool(kwargs, self.book).text


def make_recipe_tool(book: RecipeBook | None = None) -> BaseTool:
    """The chat tool; book=None loads the real file when the tool runs."""
    return RecipeTool(book=book)


RECIPE_TOOL: BaseTool = make_recipe_tool()

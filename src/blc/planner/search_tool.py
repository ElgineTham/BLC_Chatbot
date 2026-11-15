"""SEARCH_TOOL: the document search the planner can ask for (spec 018). Retrieval is a later spec."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

SEARCH_TOOL_NAME = "search_documents"
SEARCH_TOOL_DESCRIPTION = (
    "Searches the Bay Laurel Catering documents. Use it for questions about where something "
    "is kept or goes, what something is (menu items, package contents, flavors), how to do "
    "something (clean, set up, pull stock, serve) and how we do things (rules and yes/no "
    "facts). The query holds only the documents part of the question, with its key words."
)
SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "What to look up in the documents: the key words of the question.",
        },
    },
    "required": ["query"],
}


class SearchTool(BaseTool):
    """Placeholder search: returns an empty string."""

    name: str = SEARCH_TOOL_NAME
    description: str = SEARCH_TOOL_DESCRIPTION
    args_schema: dict[str, Any] | None = SEARCH_SCHEMA

    def _run(self, **kwargs: Any) -> str:
        return ""


SEARCH_TOOL: BaseTool = SearchTool()

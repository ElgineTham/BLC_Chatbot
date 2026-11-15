"""The run step: searches and tool calls of a plan (spec 019 section 4.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from langchain_core.documents import Document

from blc.flow.tool_runners import ToolRunner, run_tool
from blc.planner import Plan
from blc.planner.search_tool import SEARCH_TOOL_NAME

TOP_K = 3


class DocumentStore(Protocol):
    def similarity_search(self, query: str, k: int) -> list[Document]: ...


@dataclass(frozen=True)
class SearchResult:
    query: str
    chunks: tuple[Document, ...]


@dataclass(frozen=True)
class ToolResult:
    name: str
    args: dict[str, object]
    status: str
    text: str


def dedupe_documents(searches: tuple[SearchResult, ...]) -> tuple[Document, ...]:
    seen: set[tuple[str, object]] = set()
    documents: list[Document] = []
    for search in searches:
        for chunk in search.chunks:
            key = (chunk.page_content, chunk.metadata.get("source"))
            if key not in seen:
                seen.add(key)
                documents.append(chunk)
    return tuple(documents)


def run_plan(
    plan: Plan, store: DocumentStore, runners: Mapping[str, ToolRunner]
) -> tuple[tuple[SearchResult, ...], tuple[ToolResult, ...]]:
    """Execute every planned call in plan order."""
    searches: list[SearchResult] = []
    tools: list[ToolResult] = []
    for call in plan.calls:
        if call.name == SEARCH_TOOL_NAME:
            query = str(call.args["query"])
            searches.append(SearchResult(query, tuple(store.similarity_search(query, k=TOP_K))))
        else:
            output = run_tool(runners, call.name, call.args)
            tools.append(ToolResult(call.name, call.args, output.status, output.text))
    return tuple(searches), tuple(tools)

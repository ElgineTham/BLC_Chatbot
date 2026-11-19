"""plan_question: one model call turns a question into a Plan (spec 018)."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from blc.planner.bev_view import PLANNER_BEV_TOOL
from blc.planner.food_view import PLANNER_FOOD_TOOL
from blc.planner.prompt import PLANNER_PROMPT
from blc.planner.serv_view import PLANNER_SERV_TOOL
from blc.planner.search_tool import SEARCH_TOOL, SEARCH_TOOL_NAME
from blc.tools.recipe_tools import RECIPE_TOOL

PLANNER_TOOLS: tuple[BaseTool, ...] = (
    SEARCH_TOOL, PLANNER_BEV_TOOL, RECIPE_TOOL, PLANNER_FOOD_TOOL, PLANNER_SERV_TOOL,
)
PLAN_ROUTES: tuple[str, ...] = ("TOOL", "DOCS", "BOTH")
HISTORY_HEADER = "Recent chat history:"
QUESTION_HEADER = "Question:"
_TOOL_NAMES = frozenset(tool.name for tool in PLANNER_TOOLS)


@dataclass(frozen=True)
class PlannedCall:
    name: str
    args: dict[str, object]


@dataclass(frozen=True)
class Plan:
    route: str
    calls: tuple[PlannedCall, ...]
    fallback: bool


def _build_messages(
    question: str, history: list[dict[str, str]] | None, feedback: str | None = None
) -> list[BaseMessage]:
    parts: list[str] = []
    if history:
        lines = [f"{item['role']}: {item['content']}" for item in history]
        parts.append(HISTORY_HEADER + "\n" + "\n".join(lines))
    parts.append(f"{QUESTION_HEADER} {question}")
    if feedback:
        parts.append(feedback)
    return [SystemMessage(content=PLANNER_PROMPT), HumanMessage(content="\n\n".join(parts))]


def _clean_call(name: str, args: object, question: str) -> PlannedCall:
    clean = dict(args) if isinstance(args, dict) else {}
    if name == SEARCH_TOOL_NAME:
        query = clean.get("query")
        if not isinstance(query, str) or not query.strip():
            query = question
        clean = {"query": query}
    return PlannedCall(name, clean)


def _route_of(calls: list[PlannedCall]) -> str:
    has_search = any(call.name == SEARCH_TOOL_NAME for call in calls)
    has_tool = any(call.name != SEARCH_TOOL_NAME for call in calls)
    if has_search and has_tool:
        return "BOTH"
    return "DOCS" if has_search else "TOOL"


def plan_question(
    llm: BaseChatModel,
    question: str,
    history: list[dict[str, str]] | None = None,
    feedback: str | None = None,
) -> Plan:
    """Plan one question. Raises ValueError if question is empty or whitespace-only,
    before any call on llm. Errors raised by the model propagate unchanged."""
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    reply = llm.bind_tools(list(PLANNER_TOOLS)).invoke(_build_messages(question, history, feedback))
    calls = [
        _clean_call(raw["name"], raw.get("args"), question)
        for raw in (getattr(reply, "tool_calls", None) or [])
        if raw.get("name") in _TOOL_NAMES
    ]
    if not calls:
        fallback = PlannedCall(SEARCH_TOOL_NAME, {"query": question})
        return Plan("DOCS", (fallback,), True)
    return Plan(_route_of(calls), tuple(calls), False)

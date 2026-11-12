"""Asks the model to split a question into TOOL and DOCS parts."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from blc.router.decision import RouteDecision
from blc.router.parsing import parse_reply
from blc.router.prompt import ROUTER_SCHEMA, build_router_messages

BLANK_QUESTION_ERROR = "question must not be empty or whitespace-only"


def route_question(
    llm: BaseChatModel,
    history: list[dict[str, str]],
    question: str,
) -> RouteDecision:
    """One llm.invoke call (no tools, no documents). Raises ValueError if the question
    is blank; an unreadable reply gives a DOCS fallback. Prints nothing."""
    text = question.strip()
    if not text:
        raise ValueError(BLANK_QUESTION_ERROR)
    response = llm.invoke(build_router_messages(history, text), format=ROUTER_SCHEMA)
    return parse_reply(str(response.content), text)

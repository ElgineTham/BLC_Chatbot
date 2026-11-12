"""route_question plus the fidelity check and one retry (spec 010 section 4.2)."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from blc.router.decision import RouteDecision, RoutedPart, kind_of
from blc.router.fidelity import check_fidelity
from blc.router.items import pull_sheet_items_in
from blc.router.parsing import parse_reply
from blc.router.prompt import ROUTER_SCHEMA, build_router_messages
from blc.router.route import BLANK_QUESTION_ERROR


def _ask(
    llm: BaseChatModel, messages: list[BaseMessage], question: str
) -> tuple[RouteDecision, str]:
    response = llm.invoke(messages, format=ROUTER_SCHEMA)
    content = str(response.content)
    return parse_reply(content, question), content


def _whole_question(question: str, latest: RouteDecision) -> RouteDecision:
    all_tool = all(part.route == "TOOL" for part in latest.parts)
    route = "TOOL" if all_tool and pull_sheet_items_in(question) else "DOCS"
    parts = (RoutedPart(route, question),)
    return RouteDecision(parts, kind_of(parts), False, True)


def route_faithfully(
    llm: BaseChatModel,
    history: list[dict[str, str]],
    question: str,
) -> RouteDecision:
    """One or two llm.invoke calls. Raises ValueError if question is blank (before any
    model call). Never raises for an unreadable or unfaithful reply. Prints nothing."""
    text = question.strip()
    if not text:
        raise ValueError(BLANK_QUESTION_ERROR)
    messages = build_router_messages(history, text)
    first, first_reply = _ask(llm, messages, text)
    if first.fallback:
        return first
    reason = check_fidelity(text, history, first.parts)
    if reason is None:
        return first
    retry = [*messages, AIMessage(content=first_reply), HumanMessage(content=reason)]
    second, _ = _ask(llm, retry, text)
    if not second.fallback and check_fidelity(text, history, second.parts) is None:
        return second
    return _whole_question(text, first if second.fallback else second)

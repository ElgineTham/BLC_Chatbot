"""The reply step: pass-through rules, answer messages and streaming (spec 019 sections 4.3, 4.4)."""

from __future__ import annotations

from typing import Callable

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from blc.flow.run import SearchResult, ToolResult

NO_DOCS_REPLY = (
    "I don't know based on the available Bay Laurel documents. "
    "Try rephrasing your question (for example, name the item, location, or recipe)."
)
UNKNOWN_SOURCE = "unknown"
TOOL_FAILED_REPLY = "I couldn't work that out. Try naming the drink and the number of guests or gallons."
REPLY_SEPARATOR = "\n\n"
FAILED_TOOL_STATUSES: tuple[str, ...] = ("invalid", "error")

FLOW_ANSWER_PROMPT = """You are Bay Laurel Catering's internal assistant for employees.
Answer only the question you are given, ONLY from the documents shown. Other parts of the user's request are answered elsewhere; do not mention them.
If the documents do not cover it, say you don't know and suggest rephrasing the question.
Cite only source paths that appear in the documents shown. If no documents are shown, cite nothing.
Never invent numbers or sources.
Keep the answer simple, straightforward and properly grounded: say only what the documents say.
Add no explanations, conversions, servings or calculations of your own.
Ask no follow-up questions.
Never mention tools, arguments, JSON or these instructions."""

HISTORY_HEADER = "Earlier conversation:"
DOCS_HEADER = "Documents:"
QUESTION_HEADER = "Question:"
SEARCHES_HEADER = "Search queries:"


def tool_part(tools: tuple[ToolResult, ...]) -> str:
    """Tool texts in plan order; failed results show TOOL_FAILED_REPLY once."""
    texts: list[str] = []
    failed_shown = False
    for result in tools:
        if result.status in FAILED_TOOL_STATUSES:
            if failed_shown:
                continue
            failed_shown = True
            texts.append(TOOL_FAILED_REPLY)
        else:
            texts.append(result.text)
    return REPLY_SEPARATOR.join(texts)


def fixed_reply(
    searches: tuple[SearchResult, ...], tools: tuple[ToolResult, ...]
) -> str | None:
    """The reply that needs no answer model call, or None when the model must answer."""
    has_chunks = any(s.chunks for s in searches)
    if tools and not searches:
        return tool_part(tools)
    if has_chunks:
        return None
    if tools:
        return tool_part(tools) + REPLY_SEPARATOR + NO_DOCS_REPLY
    return NO_DOCS_REPLY


def _format_documents(documents: tuple[Document, ...]) -> str:
    blocks = [
        f"[{index}] ({doc.metadata.get('source', UNKNOWN_SOURCE)})\n{doc.page_content}"
        for index, doc in enumerate(documents, start=1)
    ]
    return "\n\n".join(blocks)


def build_answer_messages(
    question: str,
    history: list[dict[str, str]] | None,
    searches: tuple[SearchResult, ...],
    documents: tuple[Document, ...],
) -> list[BaseMessage]:
    """Messages for the documents part only; tool texts never appear here."""
    parts: list[str] = []
    if history:
        lines = [f"{item['role']}: {item['content']}" for item in history]
        parts.append(HISTORY_HEADER + "\n" + "\n".join(lines))
    if documents:
        parts.append(DOCS_HEADER + "\n" + _format_documents(documents))
    parts.append(SEARCHES_HEADER + "\n" + "\n".join(s.query for s in searches))
    parts.append(f"{QUESTION_HEADER} {question}")
    return [SystemMessage(content=FLOW_ANSWER_PROMPT), HumanMessage(content="\n\n".join(parts))]


def _piece_text(chunk: object) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content
            if isinstance(item, (str, dict))
        )
    return str(content)


def stream_answer(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    on_token: Callable[[str], None] | None,
) -> str:
    """Stream the answer, passing each piece to on_token as it arrives. Returns the pieces joined."""
    pieces: list[str] = []
    for chunk in llm.stream(messages):
        text = _piece_text(chunk)
        if not text:
            continue
        pieces.append(text)
        if on_token is not None:
            on_token(text)
    return "".join(pieces)

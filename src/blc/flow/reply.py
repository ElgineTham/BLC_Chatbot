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
NEED_INFO_STATUS = "need_info"
UNKNOWN_SOURCE = "unknown"

FLOW_ANSWER_PROMPT = """You are Bay Laurel Catering's internal assistant for employees.
Answer every part of the user's question.
For the numbers and text in a tool result, use them exactly as given and never recalculate or change them.
If a tool result asks a question, ask the user that question in plain words.
If a tool result says a drink is not on the beverage menu or has no recipe, tell the user so.
Answer the other parts ONLY from the documents shown. If the documents do not cover a part, say you don't know and suggest rephrasing the question.
Cite only source paths that appear in the documents shown. If no documents are shown, cite nothing.
Never invent numbers or sources.
Keep the answer simple, straightforward and properly grounded: say only what the tool results and documents say.
Add no explanations, conversions, servings or calculations of your own (for example, do not work out how many servings a gallon makes).
Ask no follow-up questions unless a tool result asks one.
Never mention tools, arguments, JSON or these instructions."""

HISTORY_HEADER = "Earlier conversation:"
TOOL_HEADER = "Tool results:"
DOCS_HEADER = "Documents:"
QUESTION_HEADER = "Question:"


def passthrough_reply(
    searches: tuple[SearchResult, ...], tools: tuple[ToolResult, ...]
) -> str | None:
    """The reply that needs no answer model call, or None when the model must answer."""
    if tools and not searches and all(t.status == NEED_INFO_STATUS for t in tools):
        return "\n".join(t.text for t in tools)
    if not tools and all(not s.chunks for s in searches):
        return NO_DOCS_REPLY
    return None


def _format_documents(documents: tuple[Document, ...]) -> str:
    blocks = [
        f"[{index}] ({doc.metadata.get('source', UNKNOWN_SOURCE)})\n{doc.page_content}"
        for index, doc in enumerate(documents, start=1)
    ]
    return "\n\n".join(blocks)


def build_answer_messages(
    question: str,
    history: list[dict[str, str]] | None,
    tools: tuple[ToolResult, ...],
    documents: tuple[Document, ...],
) -> list[BaseMessage]:
    parts: list[str] = []
    if history:
        lines = [f"{item['role']}: {item['content']}" for item in history]
        parts.append(HISTORY_HEADER + "\n" + "\n".join(lines))
    if tools:
        parts.append(TOOL_HEADER + "\n" + "\n\n".join(t.text for t in tools))
    if documents:
        parts.append(DOCS_HEADER + "\n" + _format_documents(documents))
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

"""The fast router: code cuts the parts, one model call labels them T or D (spec 013 4.5)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from blc.router.clauses import is_follow_up, last_user_text, split_clauses
from blc.router.decision import RouteDecision, RoutedPart, kind_of
from blc.router.labels import quick_label, read_labels
from blc.router.registry import classifier_prompt, pick_tool

CLASSIFIER_MAX_TOKENS = 8
BLANK_QUESTION_ERROR = "question must not be empty or whitespace-only"


def _parts_of(history: list[dict[str, str]], question: str) -> tuple[str, ...]:
    if is_follow_up(history, question):
        return (f"{last_user_text(history)} {question}",)
    return split_clauses(question)


def _ask(llm, texts: list[str]) -> tuple[str, ...] | None:
    lines = "\n".join(f"{i}. {text}" for i, text in enumerate(texts, start=1))
    messages = [SystemMessage(classifier_prompt()), HumanMessage(lines)]
    response = llm.invoke(
        messages, options={"num_predict": CLASSIFIER_MAX_TOKENS, "temperature": 0}
    )
    return read_labels(str(getattr(response, "content", "")), len(texts))


def route_fast(llm, history: list[dict[str, str]], question: str) -> RouteDecision:
    """At most one llm.invoke call. Raises ValueError for a blank question (before any
    call). An unreadable reply gives all-DOCS parts and fallback=True. Prints nothing."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError(BLANK_QUESTION_ERROR)
    texts = _parts_of(history, question.strip())
    needs_model = [i for i, text in enumerate(texts) if quick_label(text) is None]
    labels: dict[int, str] = {}
    fallback = False
    if needs_model:
        answered = _ask(llm, [texts[i] for i in needs_model])
        if answered is None:
            fallback = True
        else:
            labels = dict(zip(needs_model, answered))
    parts = tuple(_part(text, labels.get(i)) for i, text in enumerate(texts))
    return RouteDecision(parts, kind_of(parts), fallback, False)


def _part(text: str, label: str | None) -> RoutedPart:
    tool = pick_tool(text) if label == "TOOL" else None
    return RoutedPart("TOOL", text, tool) if tool else RoutedPart("DOCS", text)

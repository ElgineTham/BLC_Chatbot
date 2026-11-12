"""Readable text for a trace and for each of its stages (spec 011 §4.2). No I/O."""

from __future__ import annotations

from collections.abc import Sequence

from blc.router import RouteDecision
from blc.trace.stages import RetrievalStage, ToolCallLog, ToolStage, TurnTrace

HEADER = "== {name} =="
NOT_RUN = "not run"
NO_TOOL_CALL = "no tool call"
FELL_BACK = "fell back to docs"
CHUNK_PREVIEW_CHARS = 80


def _section(name: str, lines: Sequence[str]) -> str:
    return "\n".join([HEADER.format(name=name), *lines])


def _one_line(value: object, limit: int | None = None) -> str:
    text = " ".join(str(value).split())
    if limit is not None and len(text) > limit:
        text = text[:limit] + "..."
    return text


def format_prompt(question: str, history: Sequence[object]) -> str:
    return _section("prompt", [f"question: {question}", f"history items: {len(history)}"])


def format_route(route: RouteDecision | None) -> str:
    if route is None:
        return _section("route", [NOT_RUN])
    lines = [f"kind: {route.kind}"]
    lines += [f"{part.route}: {part.text}" for part in route.parts]
    if route.fallback:
        lines.append("fallback")
    if route.unfaithful:
        lines.append("unfaithful")
    return _section("route", lines)


def format_retrieval(stage: RetrievalStage | None) -> str:
    if stage is None:
        return _section("retrieval", [NOT_RUN])
    lines = [f"query: {stage.query}", f"k: {stage.k}"]
    for chunk in stage.chunks:
        preview = _one_line(chunk.text, CHUNK_PREVIEW_CHARS)
        lines.append(f"{chunk.rank}. {chunk.source}: {preview}")
    return _section("retrieval", lines)


def _format_call(call: ToolCallLog) -> str:
    mark = " (refused)" if call.refused else ""
    return f"call: {call.name} {_one_line(call.args)} -> {_one_line(call.result)}{mark}"


def format_tool(stage: ToolStage | None) -> str:
    if stage is None:
        return _section("tool", [NO_TOOL_CALL])
    lines = [f"part: {stage.part}"]
    lines += [_format_call(call) for call in stage.calls]
    lines.append(f"tool text: {stage.tool_text}" if stage.tool_text is not None else FELL_BACK)
    if stage.retried:
        lines.append("retried")
    return _section("tool", lines)


def format_reply(reply: str) -> str:
    return _section("reply", [str(reply)])


def format_trace(trace: TurnTrace) -> str:
    """The trace as readable text. Never raises. Prints nothing."""
    try:
        sections = [
            format_prompt(trace.question, trace.history),
            format_route(trace.route),
            format_retrieval(trace.retrieval),
        ]
        sections += [format_tool(stage) for stage in trace.tools] or [format_tool(None)]
        if trace.reply is not None:
            sections.append(format_reply(trace.reply))
        return "\n".join(sections)
    except Exception as error:  # a trace printer must never break the caller
        return f"(trace could not be formatted: {error})"

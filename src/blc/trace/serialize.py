"""A trace as plain data for json.dumps (spec 011 §4.3). No I/O."""

from __future__ import annotations

from blc.router import RouteDecision
from blc.trace.stages import RetrievalStage, ToolStage, TurnTrace


def _retrieval(stage: RetrievalStage | None) -> dict | None:
    if stage is None:
        return None
    chunks = [{"rank": c.rank, "source": c.source, "text": c.text} for c in stage.chunks]
    return {"query": stage.query, "k": stage.k, "chunks": chunks}


def _route(route: RouteDecision | None) -> dict | None:
    if route is None:
        return None
    return {
        "kind": route.kind,
        "fallback": route.fallback,
        "unfaithful": route.unfaithful,
        "parts": [{"route": p.route, "text": p.text} for p in route.parts],
    }


def _tool(stage: ToolStage) -> dict:
    calls = [
        {"name": c.name, "args": dict(c.args), "result": c.result, "refused": c.refused}
        for c in stage.calls
    ]
    return {
        "part": stage.part,
        "calls": calls,
        "tool_text": stage.tool_text,
        "retried": stage.retried,
    }


def trace_to_dict(trace: TurnTrace) -> dict:
    """The trace as plain data that json.dumps accepts. Never raises."""
    return {
        "question": trace.question,
        "history": [dict(item) for item in trace.history],
        "retrieval": _retrieval(trace.retrieval),
        "route": _route(trace.route),
        "tools": [_tool(stage) for stage in trace.tools],
        "reply": trace.reply,
    }

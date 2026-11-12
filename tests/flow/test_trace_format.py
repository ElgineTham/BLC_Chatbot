"""AC-1: the trace types, format_trace and trace_to_dict (EC-1 to EC-4).

Unit tests: no model, no store, nothing read under data/ (NFR-2). Both functions take data and
return data, so nothing is printed (checked with capsys).
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from blc.router import RouteDecision, RoutedPart
from blc.trace import (
    STAGE_NAMES,
    RetrievalStage,
    RetrievedChunk,
    ToolCallLog,
    ToolStage,
    TurnTrace,
    format_trace,
    trace_to_dict,
)


def sections(text):
    """Split formatted text into [(name, body)] at lines of the form '== name =='."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("== ") and s.endswith(" =="):
            out.append([s[3:-3].strip(), []])
        elif out:
            out[-1][1].append(line)
    return [(name, "\n".join(body)) for name, body in out]


def section(text, name):
    found = [body for n, body in sections(text) if n == name]
    assert found, f"no '== {name} ==' section in:\n{text}"
    return found[0]


def empty_trace(**kw):
    base = dict(question="Where is the coffee?", history=(), retrieval=None, route=None, tools=(), reply=None)
    base.update(kw)
    return TurnTrace(**base)


# ---------------------------------------------------------------- types

def test_stage_names_constant():
    """Covers: AC-1 (right), spec 3.1. STAGE_NAMES is the five names in order."""
    assert STAGE_NAMES == ("prompt", "route", "retrieval", "tool", "reply")


def test_types_have_contract_fields_and_are_frozen():
    """Covers: AC-1 (right), spec 3.1. The five dataclasses take the contract fields and are frozen."""
    chunk = RetrievedChunk(1, "data/a.md", "text")
    assert (chunk.rank, chunk.source, chunk.text) == (1, "data/a.md", "text")
    stage = RetrievalStage("q", 3, (chunk,))
    assert (stage.query, stage.k, stage.chunks) == ("q", 3, (chunk,))
    call = ToolCallLog("calculate_bev_item", {"a": 1}, "res", False)
    assert (call.name, call.args, call.result, call.refused) == ("calculate_bev_item", {"a": 1}, "res", False)
    ts = ToolStage("part", (call,), "tt", True)
    assert (ts.part, ts.calls, ts.tool_text, ts.retried) == ("part", (call,), "tt", True)
    trace = empty_trace()
    assert trace.retrieval is None and trace.route is None and trace.tools == () and trace.reply is None
    for obj, field in ((chunk, "rank"), (stage, "k"), (call, "refused"), (ts, "retried"), (trace, "reply")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, field, "x")


# ---------------------------------------------------------------- EC-1 full trace

def test_ec1_headers_in_order(full_trace):
    """Covers: AC-1 (right), EC-1. Headers prompt, route, retrieval, tool, reply appear in that order."""
    text = format_trace(full_trace)
    assert isinstance(text, str)
    names = [n for n, _ in sections(text)]
    assert names == ["prompt", "route", "retrieval", "tool", "reply"]
    positions = [text.index(f"== {n} ==") for n in names]
    assert positions == sorted(positions)


def test_ec1_prompt_section_shows_question_and_history_count(full_trace):
    """Covers: AC-1 (right), EC-1, spec 4.2. The prompt section has the question and the number of history items (3)."""
    body = section(format_trace(full_trace), "prompt")
    assert "Where are lemons kept? How many cups?" in body
    assert "3" in body


def test_ec1_route_section_lines(full_trace):
    """Covers: AC-1 (right), EC-1. The route section shows the kind and a TOOL:/DOCS: line per part."""
    body = section(format_trace(full_trace), "route")
    assert "BOTH" in body
    lines = [ln.strip() for ln in body.splitlines()]
    assert any(ln.startswith("DOCS:") and "Where are lemons kept?" in ln for ln in lines)
    assert any(ln.startswith("TOOL:") and "How many cups?" in ln for ln in lines)


def test_ec1_route_flags_words_only_when_set(full_trace):
    """Covers: AC-1 (right, wrong), EC-1. 'fallback' and 'unfaithful' appear in the route section only when the flags are set."""
    parts = (RoutedPart("DOCS", "q"),)
    plain = section(format_trace(dataclasses.replace(full_trace, route=RouteDecision(parts, "DOCS", False))), "route")
    assert "fallback" not in plain and "unfaithful" not in plain
    fb = section(format_trace(dataclasses.replace(full_trace, route=RouteDecision(parts, "DOCS", True))), "route")
    assert "fallback" in fb and "unfaithful" not in fb
    uf = section(
        format_trace(dataclasses.replace(full_trace, route=RouteDecision(parts, "DOCS", False, True))), "route")
    assert "unfaithful" in uf and "fallback" not in uf


def test_ec1_retrieval_section(full_trace):
    """Covers: AC-1 (right), EC-1. The retrieval section has the query, k, and per chunk the rank, source and start of text."""
    body = section(format_trace(full_trace), "retrieval")
    assert "Where are lemons kept? How many cups?" in body
    assert "3" in body
    lines = body.splitlines()
    first = [ln for ln in lines if "data/supplies/lemon.md" in ln]
    second = [ln for ln in lines if "data/supplies/coffee.md" in ln]
    assert first and second
    assert "1" in first[0] and "zzchunkone" in first[0]
    assert "2" in second[0] and "zzchunktwo" in second[0]
    assert body.index("data/supplies/lemon.md") < body.index("data/supplies/coffee.md")


def test_ec1_tool_section_calls_and_refused_mark(full_trace):
    """Covers: AC-1 (right, wrong), EC-1. One line per call with name, arguments and result; only the refused call is marked (refused)."""
    body = section(format_trace(full_trace), "tool")
    assert "How many cups?" in body
    refused = [ln for ln in body.splitlines() if "REFUSEDREASON" in ln]
    ran = [ln for ln in body.splitlines() if "RESULTOKTEXT" in ln]
    assert refused and ran
    assert "(refused)" in refused[0]
    assert "calculate_bev_item" in refused[0] and "50" in refused[0] and "guests" in refused[0]
    assert "(refused)" not in ran[0]
    assert "calculate_bev_item" in ran[0] and "lemonade" in ran[0]
    assert "retried" not in body


def test_ec1_reply_section(full_trace):
    """Covers: AC-1 (right), EC-1. The reply section holds the reply text."""
    assert "The final reply zzreply." in section(format_trace(full_trace), "reply")


def test_tool_section_retried_and_fell_back(full_trace):
    """Covers: AC-1 (right), spec 4.2. 'retried' appears when set; a None tool_text shows 'fell back to docs'."""
    stage = ToolStage("How many cups?", (), None, True)
    body = section(format_trace(dataclasses.replace(full_trace, tools=(stage,))), "tool")
    assert "retried" in body
    assert "fell back to docs" in body
    assert "RESULTOKTEXT" not in body


def test_tool_section_shows_tool_text(full_trace):
    """Covers: AC-1 (right), spec 4.2. The tool section shows the tool_text used for the answer."""
    stage = ToolStage("How many cups?", (), "UNIQUETOOLTEXT", False)
    body = section(format_trace(dataclasses.replace(full_trace, tools=(stage,))), "tool")
    assert "UNIQUETOOLTEXT" in body
    assert "fell back to docs" not in body


def test_one_tool_section_per_tool_stage(full_trace):
    """Covers: AC-1 (boundary), spec 4.2. Two ToolStages give two '== tool ==' sections, in order."""
    a = ToolStage("part-alpha", (), "text-alpha", False)
    b = ToolStage("part-beta", (), "text-beta", False)
    text = format_trace(dataclasses.replace(full_trace, tools=(a, b)))
    tool_bodies = [body for n, body in sections(text) if n == "tool"]
    assert len(tool_bodies) == 2
    assert "part-alpha" in tool_bodies[0] and "part-beta" in tool_bodies[1]


def test_format_trace_prints_nothing(full_trace, capsys):
    """Covers: AC-1 (right), spec 3.1. format_trace and trace_to_dict print nothing."""
    format_trace(full_trace)
    trace_to_dict(full_trace)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ---------------------------------------------------------------- EC-2 stages not run

def test_ec2_not_run_sections():
    """Covers: AC-1 (wrong), EC-2. With retrieval=None and route=None those sections say 'not run'."""
    text = format_trace(empty_trace())
    assert "not run" in section(text, "route")
    assert "not run" in section(text, "retrieval")
    assert "not run" not in section(text, "prompt")


def test_ec2_no_tool_call_section():
    """Covers: AC-1 (wrong), EC-2. With tools=() there is one tool section that says 'no tool call'."""
    text = format_trace(empty_trace())
    tool_bodies = [body for n, body in sections(text) if n == "tool"]
    assert len(tool_bodies) == 1
    assert "no tool call" in tool_bodies[0]


def test_ec2_reply_none_has_no_reply_section():
    """Covers: AC-1 (wrong), EC-2. reply=None leaves out the reply section; a reply (even empty text) is not None and shows it."""
    assert "== reply ==" not in format_trace(empty_trace())
    assert "== reply ==" in format_trace(empty_trace(reply=""))
    assert "== reply ==" in format_trace(empty_trace(reply="hello"))


def test_ec2_section_order_when_stages_missing():
    """Covers: AC-1 (boundary), EC-2. Even with nothing run, the headers keep the order prompt, route, retrieval, tool."""
    names = [n for n, _ in sections(format_trace(empty_trace()))]
    assert names == ["prompt", "route", "retrieval", "tool"]


# ---------------------------------------------------------------- EC-3 trace_to_dict

def test_ec3_full_dict_shape(full_trace):
    """Covers: AC-1 (right), EC-3. trace_to_dict follows 4.3 and survives json.dumps."""
    d = trace_to_dict(full_trace)
    assert set(d) == {"question", "history", "retrieval", "route", "tools", "reply"}
    expected = {
        "question": "Where are lemons kept? How many cups?",
        "history": [
            {"role": "user", "content": "hist-one"},
            {"role": "assistant", "content": "hist-two"},
            {"role": "user", "content": "hist-three"},
        ],
        "retrieval": {
            "query": "Where are lemons kept? How many cups?",
            "k": 3,
            "chunks": [
                {"rank": 1, "source": "data/supplies/lemon.md", "text": "zzchunkone lemons are by the sink"},
                {"rank": 2, "source": "data/supplies/coffee.md", "text": "zzchunktwo coffee is in the beverage room"},
            ],
        },
        "route": {
            "kind": "BOTH", "fallback": False, "unfaithful": False,
            "parts": [{"route": "DOCS", "text": "Where are lemons kept?"},
                      {"route": "TOOL", "text": "How many cups?"}],
        },
        "tools": [{
            "part": "How many cups?",
            "calls": [
                {"name": "calculate_bev_item", "args": {"item": "cups", "guests": 50},
                 "result": "invalid (check): REFUSEDREASON", "refused": True},
                {"name": "calculate_bev_item", "args": {"item": "cups", "drinks": ["lemonade"]},
                 "result": "RESULTOKTEXT", "refused": False},
            ],
            "tool_text": "RESULTOKTEXT", "retried": False,
        }],
        "reply": "The final reply zzreply.",
    }
    assert json.loads(json.dumps(d)) == expected


def test_ec3_none_stages_become_none():
    """Covers: AC-1 (right), EC-3. route, retrieval and reply of None become None; tools=() becomes an empty list."""
    d = trace_to_dict(empty_trace())
    assert d["route"] is None and d["retrieval"] is None and d["reply"] is None
    assert list(d["tools"]) == []
    assert list(d["history"]) == []
    assert d["question"] == "Where is the coffee?"
    json.dumps(d)


def test_ec3_flags_and_fallback_tool_text_in_dict(full_trace):
    """Covers: AC-1 (boundary), EC-3. unfaithful=True, a None tool_text and retried=True are carried into the dict."""
    route = RouteDecision((RoutedPart("TOOL", "How many cups?"),), "TOOL", False, True)
    trace = dataclasses.replace(full_trace, route=route, tools=(ToolStage("How many cups?", (), None, True),))
    d = json.loads(json.dumps(trace_to_dict(trace)))
    assert d["route"]["unfaithful"] is True and d["route"]["fallback"] is False
    assert d["tools"][0]["tool_text"] is None and d["tools"][0]["retried"] is True
    assert d["tools"][0]["calls"] == []


# ---------------------------------------------------------------- EC-4 never raises

ODD_ARGS = [
    {},
    {"obj": object()},
    {"s": {1, 2, 3}},
    {"b": b"bytes", "n": None, "f": 1.5, "nested": {"x": [object(), (1, 2)]}},
]


@pytest.mark.parametrize("args", ODD_ARGS, ids=[str(i) for i in range(len(ODD_ARGS))])
def test_ec4_odd_call_arguments_never_raise(args):
    """Covers: AC-1 (boundary), EC-4. Non-text values inside args never make either function raise."""
    stage = ToolStage("part", (ToolCallLog("calculate_bev_item", args, "res", False),), "res", False)
    trace = empty_trace(tools=(stage,))
    assert isinstance(format_trace(trace), str)
    assert isinstance(trace_to_dict(trace), dict)


def test_ec4_empty_strings_everywhere():
    """Covers: AC-1 (boundary), EC-4. Empty question, chunk text, source, call name, result and reply never raise."""
    trace = TurnTrace(
        question="", history=(),
        retrieval=RetrievalStage("", 0, (RetrievedChunk(1, "", ""),)),
        route=RouteDecision((RoutedPart("DOCS", ""),), "DOCS", True),
        tools=(ToolStage("", (ToolCallLog("", {}, "", True),), "", True),),
        reply="",
    )
    assert isinstance(format_trace(trace), str)
    assert isinstance(trace_to_dict(trace), dict)


def test_ec4_very_long_text():
    """Covers: AC-1 (boundary), EC-4. Very long text in every field never raises and the dict keeps the full text."""
    big = "word " * 50_000
    trace = TurnTrace(
        question=big, history=({"role": "user", "content": big},),
        retrieval=RetrievalStage(big, 3, (RetrievedChunk(1, "data/x.md", big),)),
        route=RouteDecision((RoutedPart("TOOL", big),), "TOOL", False),
        tools=(ToolStage(big, (ToolCallLog("n", {"k": big}, big, False),), big, False),),
        reply=big,
    )
    assert isinstance(format_trace(trace), str)
    d = trace_to_dict(trace)
    assert d["reply"] == big
    assert d["retrieval"]["chunks"][0]["text"] == big


def test_ec4_no_chunks_and_zero_parts_edge():
    """Covers: AC-1 (boundary), EC-4. A retrieval stage with chunks=() formats and converts (empty store case)."""
    trace = empty_trace(retrieval=RetrievalStage("q", 3, ()))
    text = format_trace(trace)
    body = section(text, "retrieval")
    assert "not run" not in body
    assert trace_to_dict(trace)["retrieval"] == {"query": "q", "k": 3, "chunks": []}

"""Spec 045 section 6.4 FLOW (AC-11, AC-12). Unit: scripted fake models, default runners (the always tool reads
no file)."""
from __future__ import annotations

import pytest

from blc.flow import DEFAULT_TOOL_RUNNERS, TOOL_FAILED_REPLY, ToolOutput
from blc.tools.always_tools import run_always_tool

ALWAYS = "calculate_always_items"
KEYS = {"calculate_bev_item", "scale_recipe", "calculate_food_item", "calculate_serving_utensils", ALWAYS}


# ---------------------------------------------------------------- FLOW-1 (AC-11)

def test_flow_1_runner_keys_are_exactly_the_five():
    """Covers: AC-11 (right), FLOW-1. Keys are exactly the five tool names; all callable."""
    assert set(DEFAULT_TOOL_RUNNERS) == KEYS
    assert all(callable(v) for v in DEFAULT_TOOL_RUNNERS.values())


@pytest.mark.parametrize("args,status", [
    ({"about": "tables", "tables": 4}, "ok"),
    ({"about": "both", "tables": 4}, "need_info"),
    ({"about": "tables", "tables": "two"}, "invalid"),
])
def test_flow_1_runner_matches_run_always_tool(args, status):
    """Covers: AC-11 (right/wrong), FLOW-1. The always runner returns a ToolOutput with run_always_tool's
    status and text, for ok, need_info and invalid."""
    out = DEFAULT_TOOL_RUNNERS[ALWAYS](args)
    expected = run_always_tool(args)
    assert expected.status == status
    assert isinstance(out, ToolOutput)
    assert (out.status, out.text) == (expected.status, expected.text)


def test_flow_1_runner_never_raises_on_non_mapping():
    """Covers: AC-11 (boundary), FLOW-1. Extra: non-mapping args give an invalid ToolOutput, no exception."""
    out = DEFAULT_TOOL_RUNNERS[ALWAYS](None)
    assert out.status == "invalid"


# ---------------------------------------------------------------- FLOW-2 (AC-12)

def test_flow_2_reply_is_the_tool_text(run):
    """Covers: AC-12 (right), FLOW-2. about tables, tables 4: reply equals the tool's text exactly; the answer
    model is never called; answered_by_model False; on_token gets the text once."""
    args = {"about": "tables", "tables": 4}
    r = run("Linens for 4 tables?", [[(ALWAYS, args)]])
    text = run_always_tool(args).text
    assert r.outcome.plan.route == "TOOL"
    assert r.outcome.tools[0].status == "ok"
    assert r.outcome.reply == text
    assert "Black linens: 9" in r.outcome.reply
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert r.tokens == [text]
    assert r.store.calls == []


# ---------------------------------------------------------------- FLOW-3 (AC-12)

def test_flow_3_need_info_reply_is_the_question(run):
    """Covers: AC-12 (wrong), FLOW-3. about both, tables 4 only: reply is the need_info text with the linen
    counts and the drip-tray question; no model call."""
    args = {"about": "both", "tables": 4}
    r = run("Always items for 4 tables?", [[(ALWAYS, args)]])
    text = run_always_tool(args).text
    assert r.outcome.tools[0].status == "need_info"
    assert r.outcome.reply == text
    assert "Black linens: 9" in r.outcome.reply and "Purple napkins: 8" in r.outcome.reply
    assert r.outcome.reply.strip().endswith("?")
    assert "drip trays" in r.outcome.reply.lower()
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert r.tokens == [text]


def test_flow_3_need_info_goes_into_history(run):
    """Covers: AC-12 (boundary), FLOW-3. Extra: the assistant history item is the tool's question."""
    args = {"about": "both"}
    r = run("What are the always items?", [[(ALWAYS, args)]])
    assert r.outcome.history[-1] == {"role": "assistant", "content": run_always_tool(args).text}


# ---------------------------------------------------------------- FLOW-4 (AC-12)

def test_flow_4_invalid_shows_the_friendly_sentence(run):
    """Covers: AC-12 (wrong), FLOW-4. about tables, tables "two": reply is TOOL_FAILED_REPLY; the raw invalid
    text is in neither the reply nor on_token."""
    args = {"about": "tables", "tables": "two"}
    r = run("Linens for two tables?", [[(ALWAYS, args)]])
    raw = run_always_tool(args).text
    assert raw.strip()
    assert r.outcome.tools[0].status == "invalid"
    assert r.outcome.reply == TOOL_FAILED_REPLY
    assert raw not in r.outcome.reply
    assert all(raw not in piece for piece in r.tokens)
    assert TOOL_FAILED_REPLY in "".join(r.tokens)
    assert r.llm.stream_calls == []


def test_flow_follow_up_uses_history_number(run):
    """Covers: AC-12 (right). Extra: an answer to the tool's question ('6 tables and 2 drip trays') with the
    asking turn in history runs the tool without a retry and gives the tool's text."""
    history = [
        {"role": "user", "content": "What always items do I need?"},
        {"role": "assistant", "content": "Bus tubs: check\nTowels: check\nHow many tables and drip trays?"},
    ]
    args = {"about": "both", "tables": 6, "drip_trays": 2}
    r = run("6 tables and 2 drip trays", [[(ALWAYS, args)]], history=history)
    assert r.outcome.retried is False
    assert r.outcome.reply == run_always_tool(args).text
    assert "Black linens: 13" in r.outcome.reply
    assert r.llm.stream_calls == []

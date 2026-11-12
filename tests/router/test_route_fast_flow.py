"""Spec 013 AC-4: the chat flow uses route_fast (EC-26 to EC-28).

Unit tests with the scripted fake model of conftest.py (Scripted). No Ollama, no network, nothing read
under data/ (NFR-2). The updated spec 006 flow tests are in test_answer_flow.py and tests/flow/. Spec 014: all flow calls go through
chat.run_turn (answer_with_tools is deleted).
"""

from __future__ import annotations

import chat
from blc.router import classifier_prompt
from blc.tools.bev_tools import BEV_TOOL_NAME
from langchain_core.documents import Document

DOC_MARK = "Coffee is under the coffee machine zzdocmarker."
DOCS = [Document(page_content=DOC_MARK, metadata={"source": "menu.md"})]
TOOL_Q = "How many cambros for 6 gallons of peach tea?"
VALID_CAMBROS = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}
DOCS_Q = "Where is the coffee?"


class FakeStore:
    """similarity_search(query, k=...) -> the fixed docs; records the calls."""

    def __init__(self, docs):
        self.docs = list(docs)
        self.calls = []

    def similarity_search(self, query, k=4, *args, **kwargs):
        self.calls.append((query, k))
        return list(self.docs)


# ---------------------------------------------------------------- EC-26 the flow calls route_fast

def test_run_turn_letter_router_makes_a_tool_step(monkeypatch, Scripted, ai, tc, bev_tool):
    """Covers: AC-4 (right), EC-26. run_turn(generate=True): a first scripted reply T makes a tool step; the first model call is the classifier call (system message is classifier_prompt())."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    model = Scripted(["T", "Two cambros."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    out = chat.run_turn(FakeStore(DOCS), model, [], TOOL_Q)
    assert out.route.kind == "TOOL"
    assert len(model.bound_invocations) == 1
    assert sum(len(s.calls) for s in out.tools) == 1
    assert model.plain_invocations[0][0].content == classifier_prompt()
    assert out.reply == "Two cambros."


def test_run_turn_router_d_reply_gives_no_tool_step(monkeypatch, Scripted, bev_tool):
    """Covers: AC-4 (wrong), EC-26. A first reply D for a question that goes to the model: DOCS, no bind_tools, no tool step."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    model = Scripted(["D", "In the cooler."])
    out = chat.run_turn(FakeStore(DOCS), model, [], "Where do the 5 gallon cambros go?")
    assert out.route.kind == "DOCS"
    assert model.bind_calls == [] and model.bound_invocations == []
    assert len(model.plain_invocations) == 2


def test_run_turn_old_json_router_reply_is_not_understood(monkeypatch, Scripted, bev_tool):
    """Covers: AC-4 (wrong), EC-26. A JSON reply (the old router's format) is unreadable to the new router: fallback DOCS, no tool step."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    model = Scripted(['{"parts": [{"route": "TOOL", "text": "x"}]}', "ok"])
    out = chat.run_turn(FakeStore(DOCS), model, [], TOOL_Q)
    assert out.route.fallback is True
    assert out.route.kind == "DOCS"
    assert model.bound_invocations == []


def test_run_turn_uses_the_letter_router(monkeypatch, bev_tool, Scripted, ai, tc):
    """Covers: AC-4 (right), EC-26. run_turn (through run_stages): a first scripted reply T makes a tool stage."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    model = Scripted(["T", "Two cambros."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    trace = chat.run_turn(FakeStore(DOCS), model, [], TOOL_Q)
    assert trace.route.kind == "TOOL"
    assert len(trace.tools) == 1
    assert trace.tools[0].part == TOOL_Q
    assert trace.reply == "Two cambros."
    assert model.plain_invocations[0][0].content == classifier_prompt()


# ---------------------------------------------------------------- EC-27 no router call for plain DOCS

def test_run_turn_standalone_docs_question_one_model_call(monkeypatch, Scripted, bev_tool, text_of):
    """Covers: AC-4 (right), EC-27. A standalone question with no number and no item word: one model call in all (the final one), no classifier call."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    model = Scripted(["Under the machine."])
    out = chat.run_turn(FakeStore(DOCS), model, [], DOCS_Q)
    assert len(model.plain_invocations) == 1
    assert classifier_prompt() not in text_of(model.plain_invocations[0])
    assert out.route.kind == "DOCS" and out.route.fallback is False
    assert out.reply == "Under the machine."


def test_run_turn_standalone_docs_question_makes_no_router_call(monkeypatch, bev_tool, Scripted):
    """Covers: AC-4 (right), EC-27. run_turn on a plain DOCS question: only the final call; with generate=False the model is not called at all."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)
    model = Scripted(["Under the machine."])
    trace = chat.run_turn(FakeStore(DOCS), model, [], DOCS_Q)
    assert len(model.plain_invocations) == 1
    assert trace.route.kind == "DOCS"
    silent = Scripted([])
    trace2 = chat.run_turn(FakeStore(DOCS), silent, [], DOCS_Q, generate=False)
    assert silent.plain_invocations == []
    assert trace2.reply is None and trace2.route.kind == "DOCS"


# ---------------------------------------------------------------- EC-28 keep-alive constant

def test_chat_keep_alive_constant():
    """Covers: AC-4 (right), EC-28. CHAT_KEEP_ALIVE is the string '30m'."""
    assert chat.CHAT_KEEP_ALIVE == "30m"

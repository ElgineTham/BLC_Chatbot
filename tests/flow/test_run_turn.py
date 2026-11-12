"""AC-2: run_turn returns the trace of the real flow (spec 011 section 4.4, EC-5 to EC-13).

Unit tests with a fake store and a scripted fake model (spec 006 section 5). The router reply is JSON
(spec 007) and every scripted reply is faithful to the question (spec 010), so the router makes one
call. The real calculate_bev_item runs on the Appendix A catalog through make_bev_tool(catalog); the
real tool is passed to the flow by monkeypatching chat.CHAT_TOOLS. No Ollama, no network, nothing read
under data/ (NFR-2).
"""

from __future__ import annotations

import copy

import pytest

import chat
from blc.router import RouteDecision
from blc.tool_step import REJECTED_PREFIX
from blc.tools.bev_tools import BEV_TOOL_NAME
from blc.trace import RetrievalStage, RetrievedChunk, ToolCallLog, ToolStage, TurnTrace

DOCS_Q = "Where is the coffee?"
TOOL_Q = "How many cambros for 6 gallons of peach tea?"
LEMON_Q = "Where are lemons kept?"
CUPS_Q = "How many cold cups for 45 guests?"
BOTH_Q = LEMON_Q + " " + CUPS_Q
TWO_TOOL_Q = TOOL_Q + " " + CUPS_Q
HISTORY = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]
VALID_CAMBROS = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}
VALID_CUPS = {"item": "cups", "drinks": ["lemonade"], "guests": 45}
INVENTED_GUESTS = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6], "guests": 50}


@pytest.fixture
def docs(doc):
    return [
        doc("Coffee is under the coffee machine.", "data/supplies/coffee.md"),
        doc("Sugar is in bin 4.", "data/supplies/sugar.md"),
        doc("A chunk without a source.", None),
    ]


@pytest.fixture
def run(monkeypatch, bev_tool, FakeStore, docs):
    """run(llm, question=..., history=..., store=..., generate=...) -> TurnTrace, with the Appendix A tool in use."""
    monkeypatch.setattr(chat, "CHAT_TOOLS", [bev_tool], raising=False)

    def _run(llm, question=DOCS_Q, history=None, store=None, generate=True):
        store = FakeStore(docs) if store is None else store
        return chat.run_turn(store, llm, list(HISTORY) if history is None else history, question, generate=generate)

    return _run


# ---------------------------------------------------------------- EC-5 DOCS question

def test_ec5_docs_question(run, Scripted, jparts, FakeStore, docs):
    """Covers: AC-2 (right), EC-5. Retrieval holds the store's chunks (ranks 1.., 'unknown' for a missing source), query is the question, k is TOP_K; route DOCS; no tools; reply is the final model reply."""
    store = FakeStore(docs)
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "  Under the machine.  "])
    trace = run(llm, store=store)
    assert isinstance(trace, TurnTrace)
    assert isinstance(trace.retrieval, RetrievalStage)
    assert trace.retrieval.query == DOCS_Q
    assert trace.retrieval.k == chat.TOP_K
    assert store.calls == [(DOCS_Q, chat.TOP_K)]
    assert trace.retrieval.chunks == (
        RetrievedChunk(1, "data/supplies/coffee.md", "Coffee is under the coffee machine."),
        RetrievedChunk(2, "data/supplies/sugar.md", "Sugar is in bin 4."),
        RetrievedChunk(3, "unknown", "A chunk without a source."),
    )
    assert isinstance(trace.route, RouteDecision)
    assert trace.route.kind == "DOCS"
    assert trace.tools == ()
    assert trace.reply == "Under the machine."
    assert trace.question == DOCS_Q
    assert trace.history == tuple(HISTORY)


def test_ec5_question_is_stripped(run, Scripted, jparts):
    """Covers: AC-2 (boundary), EC-5. The question in the trace and the search query are the stripped question."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "ok"])
    trace = run(llm, question="  \t" + DOCS_Q + " \n")
    assert trace.question == DOCS_Q
    assert trace.retrieval.query == DOCS_Q


def test_ec5_history_is_the_one_passed_and_is_not_mutated(run, Scripted, jparts):
    """Covers: AC-2 (right), EC-5. trace.history equals the history passed (as a tuple) and the caller's list is unchanged."""
    history = copy.deepcopy(HISTORY)
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "ok"])
    trace = run(llm, history=history)
    assert trace.history == tuple(HISTORY)
    assert history == HISTORY


def test_ec5_empty_history(run, Scripted, jparts):
    """Covers: AC-2 (boundary), EC-5. An empty history gives history == ()."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "ok"])
    assert run(llm, history=[]).history == ()


def test_ec5_fewer_chunks_than_top_k(run, Scripted, jparts, FakeStore, doc):
    """Covers: AC-2 (boundary), EC-5. One chunk found: one RetrievedChunk with rank 1; k still TOP_K."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "ok"])
    trace = run(llm, store=FakeStore([doc("only chunk", "data/a.md")]))
    assert trace.retrieval.chunks == (RetrievedChunk(1, "data/a.md", "only chunk"),)
    assert trace.retrieval.k == chat.TOP_K


# ---------------------------------------------------------------- EC-6 TOOL question

def test_ec6_tool_question(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (right), EC-6. One ToolStage holds the call as sent, its result, refused=False, and tool_text equal to the tool's result."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q)), "Bring two cambros."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    trace = run(llm, question=TOOL_Q)
    assert trace.route.kind == "TOOL"
    assert len(trace.tools) == 1
    stage = trace.tools[0]
    assert isinstance(stage, ToolStage)
    assert stage.part == TOOL_Q
    assert len(stage.calls) == 1
    call = stage.calls[0]
    assert isinstance(call, ToolCallLog)
    assert call.name == BEV_TOOL_NAME
    assert call.args == VALID_CAMBROS
    assert call.refused is False
    assert call.result.strip() and not call.result.strip().lower().startswith(("invalid", "error"))
    assert stage.tool_text == call.result
    assert stage.retried is False
    assert trace.reply == "Bring two cambros."
    assert trace.retrieval is not None  # retrieval runs before routing, on the whole question


def test_ec6_two_tool_parts_two_stages(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (right), EC-6 (extra). Two TOOL parts give two ToolStages in order, each with its own part text and call."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q), ("TOOL", CUPS_Q)), "Both done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "a")]), ai("", [tc(BEV_TOOL_NAME, VALID_CUPS, "b")])],
    )
    trace = run(llm, question=TWO_TOOL_Q)
    assert [s.part for s in trace.tools] == [TOOL_Q, CUPS_Q]
    assert [s.calls[0].args for s in trace.tools] == [VALID_CAMBROS, VALID_CUPS]
    assert [s.tool_text for s in trace.tools] == [s.calls[0].result for s in trace.tools]


# ---------------------------------------------------------------- EC-7 BOTH question

def test_ec7_both_question(run, Scripted, jparts, ai, tc, FakeStore, docs):
    """Covers: AC-2 (right), EC-7. BOTH: retrieval set (on the whole question), route BOTH, one ToolStage for the TOOL part only."""
    store = FakeStore(docs)
    llm = Scripted(
        [jparts(("DOCS", LEMON_Q), ("TOOL", CUPS_Q)), "Lemons are ... bring cups."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    trace = run(llm, question=BOTH_Q, store=store)
    assert trace.retrieval is not None and len(trace.retrieval.chunks) == 3
    assert trace.retrieval.query == BOTH_Q
    assert store.calls == [(BOTH_Q, chat.TOP_K)]
    assert trace.route.kind == "BOTH"
    assert [p.route for p in trace.route.parts] == ["DOCS", "TOOL"]
    assert len(trace.tools) == 1
    assert trace.tools[0].part == CUPS_Q
    assert trace.reply == "Lemons are ... bring cups."


# ---------------------------------------------------------------- EC-8 refused calls

def test_ec8_refused_call_then_corrected_call(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (right, wrong), EC-8. An invented guest count is refused by the argument check (refused=True, result starts with REJECTED_PREFIX); the corrected call after it has refused=False; tool_text is the second result."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q)), "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, INVENTED_GUESTS, "bad")]),
               ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "good")])],
    )
    trace = run(llm, question=TOOL_Q)
    calls = trace.tools[0].calls
    assert len(calls) == 2
    assert calls[0].refused is True
    assert calls[0].result.startswith(REJECTED_PREFIX)
    assert calls[0].args == INVENTED_GUESTS
    assert calls[1].refused is False
    assert not calls[1].result.startswith(REJECTED_PREFIX)
    assert trace.tools[0].tool_text == calls[1].result


def test_ec8_refused_is_true_exactly_for_check_refusals(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (wrong), EC-8 (extra). An unknown tool name and a call the calculator calls invalid are not 'refused'; only the argument check sets it."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q)), "Done."],
        bound=[ai("", [tc("made_up_tool", {"q": 1}, "u")]),
               ai("", [tc(BEV_TOOL_NAME, {"item": "pans"}, "i")]),
               ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "g")])],
    )
    calls = run(llm, question=TOOL_Q).tools[0].calls
    assert len(calls) == 3
    assert calls[0].name == "made_up_tool" and calls[0].refused is False
    assert calls[0].result == "error: unknown tool made_up_tool"
    assert calls[1].result.strip().lower().startswith("invalid") and not calls[1].result.startswith(REJECTED_PREFIX)
    assert calls[1].refused is False
    assert calls[2].refused is False


def test_ec8_round_limit_with_refused_calls(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (boundary), EC-8. Refused calls forever: MAX_TOOL_ROUNDS calls, all refused=True, tool_text is TOOL_LIMIT_REPLY."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q)), "Sorry."],
        bound=[ai("", [tc(BEV_TOOL_NAME, INVENTED_GUESTS, "x")])],
        repeat_last=True,
    )
    stage = run(llm, question=TOOL_Q).tools[0]
    assert len(stage.calls) == chat.MAX_TOOL_ROUNDS
    assert all(c.refused for c in stage.calls)
    assert stage.tool_text == chat.TOOL_LIMIT_REPLY


# ---------------------------------------------------------------- EC-9 generate=False

def test_ec9_generate_false_docs(run, Scripted, jparts):
    """Covers: AC-2 (right), EC-9. generate=False on a DOCS question: reply None and the model is invoked only for the router (one call; a second would fail the script)."""
    llm = Scripted([jparts(("DOCS", DOCS_Q))])
    trace = run(llm, generate=False)
    assert trace.reply is None
    assert len(llm.plain_invocations) == 1
    assert llm.bind_calls == []
    assert trace.retrieval is not None and trace.route is not None


def test_ec9_generate_false_tool(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (right), EC-9. generate=False on a TOOL question: the tool step still runs and is traced; only the router call is made on the plain model."""
    llm = Scripted([jparts(("TOOL", TOOL_Q))], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    trace = run(llm, question=TOOL_Q, generate=False)
    assert trace.reply is None
    assert len(llm.plain_invocations) == 1
    assert len(llm.bound_invocations) == 1
    assert len(trace.tools) == 1 and trace.tools[0].tool_text is not None


def test_ec9_generate_true_makes_the_final_call(run, Scripted, jparts):
    """Covers: AC-2 (wrong), EC-9. With generate=True (the default) the final call is made: router then final on the plain model."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "Final."])
    trace = run(llm)
    assert len(llm.plain_invocations) == 2
    assert trace.reply == "Final."


def test_ec9_generate_defaults_to_true(Scripted, jparts, FakeStore, docs):
    """Covers: AC-2 (right), EC-9. run_turn called without generate makes the final call."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "Final."])
    trace = chat.run_turn(FakeStore(docs), llm, [], DOCS_Q)
    assert trace.reply == "Final."


# ---------------------------------------------------------------- EC-10 empty store

def test_ec10_empty_store(run, Scripted, FakeStore):
    """Covers: AC-2 (wrong), EC-10. No chunks: route None, tools (), retrieval.chunks (), the model is never invoked, reply is the unknown-retrieval reply."""
    llm = Scripted([])
    trace = run(llm, store=FakeStore([]))
    assert trace.route is None
    assert trace.tools == ()
    assert trace.retrieval is not None
    assert trace.retrieval.chunks == ()
    assert trace.retrieval.query == DOCS_Q and trace.retrieval.k == chat.TOP_K
    assert trace.reply == chat.unknown_retrieval_reply()
    assert llm.plain_invocations == [] and llm.bind_calls == [] and llm.bound_invocations == []


def test_ec10_empty_store_generate_false(run, Scripted, FakeStore):
    """Covers: AC-2 (boundary), EC-10. Empty store with generate=False: reply None, model never invoked."""
    llm = Scripted([])
    trace = run(llm, store=FakeStore([]), generate=False)
    assert trace.reply is None
    assert trace.route is None and trace.tools == ()
    assert llm.plain_invocations == [] and llm.bind_calls == []


# ---------------------------------------------------------------- EC-11 fallback to DOCS

def test_ec11_tool_part_falls_back_to_docs(run, Scripted, jparts, ai):
    """Covers: AC-2 (wrong), EC-11. The model makes no call twice: tool_text None, calls as made (none), retried True; the route is still TOOL."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q)), "I don't know."],
        bound=[ai("Two cambros."), ai("Still two cambros.")],
    )
    trace = run(llm, question=TOOL_Q)
    stage = trace.tools[0]
    assert stage.tool_text is None
    assert stage.calls == ()
    assert stage.retried is True
    assert trace.route.kind == "TOOL"
    assert trace.reply == "I don't know."


def test_ec11_no_call_then_call_is_retried_not_fallback(run, Scripted, jparts, ai, tc):
    """Covers: AC-2 (right), EC-11 (extra). No call first, a call after the reminder: retried True and tool_text is set."""
    llm = Scripted(
        [jparts(("TOOL", TOOL_Q)), "Done."],
        bound=[ai("I think two."), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    stage = run(llm, question=TOOL_Q).tools[0]
    assert stage.retried is True
    assert len(stage.calls) == 1
    assert stage.tool_text == stage.calls[0].result


# ---------------------------------------------------------------- EC-12 blank question

@pytest.mark.parametrize("question", ["", " ", "   ", "\n", "\t \n"])
@pytest.mark.parametrize("generate", [True, False])
def test_ec12_blank_question_raises_before_any_call(NoCallStore, NoCallLLM, question, generate):
    """Covers: AC-2 (wrong), EC-12 (boundary). A blank question raises ValueError and touches neither the store nor the model."""
    with pytest.raises(ValueError):
        chat.run_turn(NoCallStore(), NoCallLLM(), [], question, generate=generate)


def test_ec12_single_character_question_is_accepted(run, Scripted, jparts):
    """Covers: AC-2 (boundary), EC-12. A one-character question is not blank."""
    llm = Scripted([jparts(("DOCS", "?")), "ok"])
    assert run(llm, question="?").question == "?"


# ---------------------------------------------------------------- EC-13 summarised history

def test_ec13_long_history_is_summarised(run, Scripted, jparts):
    """Covers: AC-2 (right), EC-13. A history over the token limit is summarised: trace.history is the one summary item, not the original history; the caller's list is untouched."""
    big = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "catering menu details " * 130}
        for i in range(20)
    ]
    snapshot = copy.deepcopy(big)
    llm = Scripted(["SUMMARY-XYZ", jparts(("DOCS", DOCS_Q)), "Final."])
    trace = run(llm, history=big)
    assert big == snapshot
    assert len(trace.history) == 1
    assert trace.history[0]["role"] == "summary"
    assert "SUMMARY-XYZ" in trace.history[0]["content"]
    assert trace.reply == "Final."


def test_ec13_short_history_is_not_summarised(run, Scripted, jparts):
    """Covers: AC-2 (boundary), EC-13. A short history is used as it is and the model gets no summary call (router then final only)."""
    llm = Scripted([jparts(("DOCS", DOCS_Q)), "Final."])
    trace = run(llm)
    assert trace.history == tuple(HISTORY)
    assert len(llm.plain_invocations) == 2

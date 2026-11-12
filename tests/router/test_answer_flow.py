"""AC-2: the chat flow (EC-4 to EC-13). Router, then tool steps, then the final call.

Rewritten for spec 014: these tests used to call `chat.answer_with_tools` (deleted). They now call the real
flow, `chat.run_turn(store, llm, history, question, generate=True)`, through the `run` fixture below, which
passes a fake store (similarity_search(query, k=...)) and patches chat.CHAT_TOOLS. Every assertion of the
earlier version is kept; only the way the result is read changed:
  out.reply                -> trace.reply
  out.route                -> trace.route
  out.parts[i].part        -> trace.route.parts[i]
  out.parts[i].tool_text   -> the matching ToolStage's tool_text (one ToolStage per TOOL part, in order)
  out.parts[i].tool_calls  -> the matching ToolStage's calls
  out.tool_calls           -> all calls of all ToolStages, in order (helper `calls_of`)
  out.retried              -> ToolStage.retried

Unit tests with a scripted fake model: llm.invoke replies come from `plain` (router first when the router
needs the model, final last), bound.invoke replies from `bound`. The real calculate_bev_item runs on the
Appendix A catalog through make_bev_tool(catalog); no Ollama, no network, nothing read under data/ (NFR-2).
The router is the letter router of spec 013 (T or D, one letter per part sent to the model; a standalone
question with no number and no item word needs no router call).

Dropped (types or functions deleted by spec 014; see the report for where each is covered):
- test_part_result_and_tool_answer_are_frozen_dataclasses (PartResult/ToolAnswer gone; the frozen trace types
  are covered by tests/flow/test_trace_format.py::test_types_have_contract_fields_and_are_frozen)
- test_ec13_answer_from_context_returns_reply and test_ec13_answer_from_context_delegates
  (answer_from_context gone; the reply of the DOCS flow is asserted in test_ec4_docs_only)
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, ToolMessage

import chat
from blc.router import RouteDecision, RoutedPart
from blc.tools.bev_tools import BEV_TOOL_NAME
from blc.trace import TurnTrace

DOC_MARK = "Coffee is under the coffee machine zzdocmarker."
DOCS = [Document(page_content=DOC_MARK, metadata={"source": "menu.md"})]
HISTORY = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]
QUESTION = "Where is the coffee?"  # spec 013: no number, no item word, a starter: DOCS with no router call
PEACH_Q = "How many cambros for 6 gallons of peach tea?"
CUPS_Q = "How many cold cups for 45 guests?"
BOTH_Q = QUESTION + " " + CUPS_Q  # parts: (DOCS, QUESTION), (TOOL, CUPS_Q); only the second goes to the model
TOOL_FIRST_Q = CUPS_Q + " " + QUESTION
TWO_TOOL_Q = PEACH_Q + " " + CUPS_Q
TOOL_THEN_DOCS_Q = QUESTION + " " + PEACH_Q
VALID_CAMBROS = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}
VALID_CUPS = {"item": "cups", "drinks": ["lemonade"], "guests": 45}
INVALID = {"item": "pans"}


@pytest.fixture
def run(run_turn_with):
    """run(model, tools, docs=None, history=None, question=QUESTION) -> TurnTrace of the real flow (generate=True)."""

    def _run(model, tools, docs=None, history=None, question=QUESTION):
        return run_turn_with(
            model,
            question,
            tools,
            DOCS if docs is None else docs,
            history=[dict(m) for m in HISTORY] if history is None else history,
        )

    return _run


def calls_of(trace):
    return [c for stage in trace.tools for c in stage.calls]


def tool_messages(messages):
    return [m for m in messages if isinstance(m, ToolMessage)]


def final_text(model, text_of):
    return text_of(model.plain_invocations[-1])


# ---------------------------------------------------------------- constants

def test_prompts_are_nonempty_strings():
    """Covers: AC-2 (right). TOOL_PROMPT and ANSWER_PROMPT exist and are non-trivial strings."""
    for prompt in (chat.TOOL_PROMPT, chat.ANSWER_PROMPT):
        assert isinstance(prompt, str) and len(prompt.strip()) > 20
    assert chat.TOOL_PROMPT != chat.ANSWER_PROMPT


def test_tool_prompt_names_the_tool_and_items():
    """Covers: AC-2 (right), spec 4.3. TOOL_PROMPT names calculate_bev_item and the five item values."""
    for word in (BEV_TOOL_NAME, "gallons", "cambros", "cups", "supplies", "everything", "guests"):
        assert word in chat.TOOL_PROMPT


def test_safety_net_is_removed():
    """Covers: AC-2 (wrong), spec 3.2 'Removed'. TOOL_HINT_WORDS no longer exists."""
    assert not hasattr(chat, "TOOL_HINT_WORDS")


# ---------------------------------------------------------------- EC-4 DOCS only

def test_ec4_docs_only(run, Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. DOCS route: no bind_tools, docs in the final messages, no tool call. Spec 013: the question needs no router call, so there is 1 llm.invoke call (the final one) instead of 2."""
    model = Scripted(["  Under the machine.  \n"])
    out = run(model, (bev_tool,))
    assert isinstance(out, TurnTrace)
    assert out.reply == "Under the machine."
    assert model.bind_calls == []
    assert len(model.plain_invocations) == 1
    assert model.bound_invocations == []
    assert out.tools == ()
    assert calls_of(out) == []
    assert out.route.kind == "DOCS"
    assert out.route.fallback is False
    assert len(out.route.parts) == 1
    assert out.route.parts[0] == RoutedPart("DOCS", QUESTION)
    final = model.plain_invocations[-1]
    assert DOC_MARK in text_of(final)
    assert not tool_messages(final)


def test_ec4_docs_only_with_router_letter(run, Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. A DOCS question that does go to the model (it has a number): reply D gives a DOCS part, 2 llm.invoke calls, no bind_tools, docs in the final messages."""
    q = "Where do the 5 gallon cambros go?"
    model = Scripted(["D", "  Under the machine.  \n"])
    out = run(model, (bev_tool,), question=q)
    assert out.reply == "Under the machine."
    assert model.bind_calls == []
    assert len(model.plain_invocations) == 2
    assert out.route.kind == "DOCS" and out.route.fallback is False
    assert out.route.parts[0] == RoutedPart("DOCS", q)
    assert DOC_MARK in text_of(model.plain_invocations[-1])


def test_ec4_final_call_shape(run, Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. Final messages: SystemMessage(ANSWER_PROMPT), the history, then the original question."""
    model = Scripted(["Under the machine."])
    run(model, (bev_tool,))
    final = model.plain_invocations[-1]
    assert isinstance(final[0], SystemMessage)
    assert chat.ANSWER_PROMPT in final[0].content
    body = text_of(final)
    assert "earlier question zebra" in body and "earlier answer giraffe" in body
    assert QUESTION in body
    assert body.index("earlier question zebra") < body.index(QUESTION)
    assert str(final[-1].content).count(QUESTION) >= 1  # the question is in the last (human) message


def test_ec4_router_call_is_first_and_sees_question_and_history(run, Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. When the router needs the model, its call is the first llm.invoke: it holds the question and history (a follow-up joins them) but no documents. Spec 013: the question is a follow-up so the history reaches the router inside the joined part."""
    follow_up = "55 guests."
    model = Scripted(["D", "Under the machine."])
    run(model, (bev_tool,), question=follow_up)
    first = text_of(model.plain_invocations[0])
    assert follow_up in first
    assert "earlier question zebra" in first
    assert DOC_MARK not in first
    assert chat.ANSWER_PROMPT not in first


# ---------------------------------------------------------------- EC-5 TOOL only

def test_ec5_tool_only(run, Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-5. One tool step: the real tool runs once; the final messages hold its result and no documents."""
    model = Scripted(
        ["T", "Bring two cambros."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "id-5")])],
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert out.reply == "Bring two cambros."
    calls = calls_of(out)
    assert len(calls) == 1
    rec = calls[0]
    assert (rec.name, rec.args) == (BEV_TOOL_NAME, VALID_CAMBROS)
    assert not rec.result.strip().lower().startswith(("invalid", "error"))
    assert len(out.tools) == 1
    assert out.tools[0].tool_text == rec.result
    assert out.tools[0].calls == (rec,)
    assert out.route.kind == "TOOL"
    assert out.tools[0].retried is False
    assert len(model.bind_calls) == 1 and model.bind_calls[0] == [bev_tool]
    assert len(model.bound_invocations) == 1
    assert len(model.plain_invocations) == 2
    final = final_text(model, text_of)
    assert rec.result in final
    assert DOC_MARK not in final
    assert PEACH_Q in final


def test_ec5_tool_step_messages_have_no_documents_and_no_history(run, Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-5. The tool step gets TOOL_PROMPT and the part's text only: no document text, no history, and (spec 013: with a BOTH question) not the other part of the original question."""
    model = Scripted(
        ["T", "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    run(model, (bev_tool,), question=TOOL_THEN_DOCS_Q)
    step = model.bound_invocations[0]
    assert isinstance(step[0], SystemMessage)
    assert chat.TOOL_PROMPT in step[0].content
    body = text_of(step)
    assert PEACH_Q in body
    assert DOC_MARK not in body
    assert "zebra" not in body and "giraffe" not in body
    assert TOOL_THEN_DOCS_Q not in body
    assert QUESTION not in body
    assert chat.ANSWER_PROMPT not in body


def test_ec5_final_call_has_no_tool_bound_and_is_plain_invoke(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-5, spec 4.5. The tool is bound once for the tool step; the final call is a plain llm.invoke (the last one)."""
    model = Scripted(
        ["T", "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    run(model, (bev_tool,), question=PEACH_Q)
    assert len(model.bind_calls) == 1
    assert len(model.plain_invocations) == 2
    assert model.plain_script == [] and model.bound_script == []


def test_ec5_final_message_labels_the_tool_part_question(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-5, spec 4.5. The final human message carries the TOOL part's question next to its result."""
    model = Scripted(
        ["T", "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    last = str(model.plain_invocations[-1][-1].content)
    assert PEACH_Q in last
    assert calls_of(out)[0].result in last


def test_ec5_tool_message_id_not_needed_when_step_ends_after_valid_round(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-5. A valid first round ends the step: the model is not asked again (script of one reply suffices)."""
    model = Scripted(["T", "Done."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    run(model, (bev_tool,), question=PEACH_Q)
    assert len(model.bound_invocations) == 1


# ---------------------------------------------------------------- EC-6 BOTH

def test_ec6_both(run, Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-6. DOCS then TOOL: one tool step for the TOOL part; the final messages hold the docs and the tool result. Spec 013: only the TOOL part goes to the model, so the router reply is one letter."""
    model = Scripted(
        ["T", "Lemons are kept ... and bring cups."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    out = run(model, (bev_tool,), question=BOTH_Q)
    assert out.route.kind == "BOTH"
    assert len(out.route.parts) == 2
    docs_part, tool_part = out.route.parts
    assert docs_part == RoutedPart("DOCS", QUESTION)
    assert tool_part == RoutedPart("TOOL", CUPS_Q, "calculate_bev_item")
    assert len(out.tools) == 1  # the DOCS part has no tool stage
    stage = out.tools[0]
    assert stage.part == CUPS_Q
    assert stage.tool_text == calls_of(out)[0].result
    assert len(calls_of(out)) == 1
    assert len(model.bound_invocations) == 1
    assert CUPS_Q in text_of(model.bound_invocations[0])
    assert QUESTION not in text_of(model.bound_invocations[0])
    final = final_text(model, text_of)
    assert DOC_MARK in final
    assert stage.tool_text in final
    assert out.reply == "Lemons are kept ... and bring cups."


def test_ec6_both_tool_first(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-6. TOOL then DOCS: parts keep the question's order."""
    model = Scripted(
        ["T", "ok"],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    out = run(model, (bev_tool,), question=TOOL_FIRST_Q)
    assert [p.route for p in out.route.parts] == ["TOOL", "DOCS"]
    assert len(out.tools) == 1 and out.tools[0].tool_text is not None


# ---------------------------------------------------------------- EC-7 two TOOL parts

def test_ec7_two_tool_parts(run, Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-7. Two tool steps in order; the calls list both calls in order; the tool is bound once."""
    model = Scripted(
        ["TT", "Both done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "a")]), ai("", [tc(BEV_TOOL_NAME, VALID_CUPS, "b")])],
    )
    out = run(model, (bev_tool,), question=TWO_TOOL_Q)
    calls = calls_of(out)
    assert out.route.kind == "TOOL"
    assert [r.args for r in calls] == [VALID_CAMBROS, VALID_CUPS]
    assert len(out.tools) == 2
    assert out.tools[0].calls == (calls[0],)
    assert out.tools[1].calls == (calls[1],)
    assert out.tools[0].tool_text == calls[0].result
    assert out.tools[1].tool_text == calls[1].result
    assert len(model.bind_calls) == 1
    assert len(model.bound_invocations) == 2
    assert PEACH_Q in text_of(model.bound_invocations[0]) and CUPS_Q not in text_of(model.bound_invocations[0])
    assert CUPS_Q in text_of(model.bound_invocations[1]) and PEACH_Q not in text_of(model.bound_invocations[1])
    final = final_text(model, text_of)
    assert out.tools[0].tool_text in final and out.tools[1].tool_text in final
    assert DOC_MARK not in final
    assert len(model.plain_invocations) == 2


# ---------------------------------------------------------------- EC-8 / EC-9 rounds

def test_ec8_invalid_then_fixed(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-8. First result starts with 'invalid'; the model is asked again; tool_text is the second result."""
    model = Scripted(
        ["T", "Fixed answer."],
        bound=[ai("", [tc(BEV_TOOL_NAME, INVALID, "bad")]), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "good")])],
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    calls = calls_of(out)
    assert len(model.bound_invocations) == 2
    assert len(calls) == 2
    first, second = calls
    assert first.result.strip().lower().startswith("invalid")
    assert not second.result.strip().lower().startswith(("invalid", "error"))
    assert out.tools[0].tool_text == second.result
    assert out.tools[0].calls == tuple(calls)
    assert out.reply == "Fixed answer."
    tms = tool_messages(model.bound_invocations[1])
    assert len(tms) == 1
    assert tms[0].tool_call_id == "bad"
    assert tms[0].content == first.result


def test_ec9_never_valid_hits_round_limit(run, Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (wrong, boundary), EC-9. Invalid calls forever: after MAX_TOOL_ROUNDS rounds tool_text is TOOL_LIMIT_REPLY."""
    model = Scripted(
        ["T", "Sorry."],
        bound=[ai("", [tc(BEV_TOOL_NAME, INVALID, "x")])],
        repeat_last=True,
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert len(model.bound_invocations) == chat.MAX_TOOL_ROUNDS
    assert len(calls_of(out)) == chat.MAX_TOOL_ROUNDS
    assert out.tools[0].tool_text == chat.TOOL_LIMIT_REPLY
    assert out.tools[0].retried is False
    assert len(model.plain_invocations) == 2  # the final call still happens, once


def test_ec9_valid_on_last_allowed_round(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-9. Valid on round MAX_TOOL_ROUNDS is accepted, not the limit reply."""
    bound = [ai("", [tc(BEV_TOOL_NAME, INVALID, f"i{n}")]) for n in range(chat.MAX_TOOL_ROUNDS - 1)]
    bound.append(ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "ok")]))
    model = Scripted(["T", "Done."], bound=bound)
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert len(model.bound_invocations) == chat.MAX_TOOL_ROUNDS
    assert out.tools[0].tool_text == calls_of(out)[-1].result != chat.TOOL_LIMIT_REPLY


def test_round_with_two_valid_calls_joins_results_with_newline(run, Scripted, ai, tc, make_tool):
    """Covers: AC-2 (boundary), spec 4.3. Several valid calls in one round: tool_text is the results joined with a newline, in call order."""
    t, calls = make_tool(BEV_TOOL_NAME, result="R-ONE")
    model = Scripted(
        ["T", "ok"],
        bound=[ai("", [tc(BEV_TOOL_NAME, {"x": "1"}, "a"), tc(BEV_TOOL_NAME, {"x": "2"}, "b")])],
    )
    out = run(model, (t,), question=PEACH_Q)
    assert calls == [{"x": "1"}, {"x": "2"}]
    assert len(calls_of(out)) == 2
    assert out.tools[0].tool_text == "R-ONE\nR-ONE"
    assert len(model.bound_invocations) == 1


# ---------------------------------------------------------------- EC-10 no call

def test_ec10_no_call_then_call(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-10. No call first, a call after the reminder: retried=True and the tool runs."""
    model = Scripted(
        ["T", "Done."],
        bound=[ai("I think two cambros."), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert out.tools[0].retried is True
    assert len(model.bound_invocations) == 2
    assert len(model.bound_invocations[1]) > len(model.bound_invocations[0])  # a reminder was added
    assert len(calls_of(out)) == 1
    assert out.tools[0].tool_text == calls_of(out)[0].result


def test_ec10_no_call_twice_falls_back_to_docs(run, Scripted, ai, bev_tool, text_of):
    """Covers: AC-2 (wrong), EC-10. No call twice: tool_text None, no calls, the final messages contain the docs."""
    model = Scripted(
        ["T", "I don't know."],
        bound=[ai("Two cambros."), ai("Still two cambros.")],
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert out.tools[0].retried is True
    assert len(model.bound_invocations) == 2  # asked exactly twice, no third time
    assert calls_of(out) == []
    assert out.route.parts[0].route == "TOOL"
    assert out.tools[0].tool_text is None
    assert out.tools[0].calls == ()
    final = final_text(model, text_of)
    assert DOC_MARK in final
    assert out.reply == "I don't know."


def test_ec10_fallen_back_part_next_to_working_tool_part(run, Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (boundary), EC-10. A fallen-back TOOL part does not stop a later TOOL part; docs and the later result both reach the final call."""
    model = Scripted(
        ["TT", "ok"],
        bound=[ai("no"), ai("still no"), ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    out = run(model, (bev_tool,), question=TWO_TOOL_Q)
    assert len(out.tools) == 2
    assert out.tools[0].tool_text is None
    assert out.tools[1].tool_text == calls_of(out)[0].result
    assert len(calls_of(out)) == 1
    final = final_text(model, text_of)
    assert DOC_MARK in final
    assert out.tools[1].tool_text in final


def test_ec10_no_call_on_valid_first_try_is_not_retried(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (wrong), EC-10. A tool call on the first reply never sets retried."""
    model = Scripted(["T", "ok"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    assert run(model, (bev_tool,), question=PEACH_Q).tools[0].retried is False


# ---------------------------------------------------------------- EC-11 router fallback

def test_ec11_router_fallback_behaves_like_docs(run, Scripted, bev_tool, text_of):
    """Covers: AC-2 (wrong), EC-11. An unreadable router reply: one DOCS part with the whole question, fallback=True, no tool."""
    model = Scripted(["I think this is a tool question.", "Under the machine."])
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert out.route.fallback is True
    assert out.route.kind == "DOCS"
    assert out.route.parts == (RoutedPart("DOCS", PEACH_Q),)
    assert model.bind_calls == []
    assert len(model.plain_invocations) == 2
    assert out.tools == ()
    assert DOC_MARK in final_text(model, text_of)
    assert out.reply == "Under the machine."


# ---------------------------------------------------------------- EC-12 unknown tool

def test_ec12_unknown_tool_name(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (wrong), EC-12. An unknown tool name gives 'error: unknown tool <name>', is recorded and sent back, and the next round runs."""
    model = Scripted(
        ["T", "Done."],
        bound=[ai("", [tc("made_up_tool", {"q": 1}, "u1")]), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "g1")])],
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    calls = calls_of(out)
    assert (calls[0].name, calls[0].args, calls[0].result) == (
        "made_up_tool", {"q": 1}, "error: unknown tool made_up_tool")
    tms = tool_messages(model.bound_invocations[1])
    assert tms[0].tool_call_id == "u1"
    assert tms[0].content == "error: unknown tool made_up_tool"
    assert len(calls) == 2
    assert out.tools[0].tool_text == calls[1].result


def test_ec12_unknown_tool_forever_hits_limit(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-12, EC-9. 'error...' results count as failed rounds: after MAX_TOOL_ROUNDS rounds tool_text is TOOL_LIMIT_REPLY."""
    model = Scripted(
        ["T", "Sorry."],
        bound=[ai("", [tc("nope", {}, "n")])],
        repeat_last=True,
    )
    out = run(model, (bev_tool,), question=PEACH_Q)
    assert len(model.bound_invocations) == chat.MAX_TOOL_ROUNDS
    assert out.tools[0].tool_text == chat.TOOL_LIMIT_REPLY
    assert all(r.result == "error: unknown tool nope" for r in calls_of(out))


# ---------------------------------------------------------------- EC-13 printing, history, reply

def test_ec13_nothing_printed_and_history_untouched(run, Scripted, ai, tc, bev_tool, capsys):
    """Covers: AC-2 (boundary), EC-13. A full TOOL turn prints nothing and does not change the history list."""
    history = [dict(m) for m in HISTORY]
    model = Scripted(["T", "ok"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    run(model, (bev_tool,), history=history, question=PEACH_Q)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert history == HISTORY


def test_reply_is_stripped_of_surrounding_whitespace(run, Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), spec 4.5. The reply is the final call's content, stripped."""
    model = Scripted(["T", "\n  Two cambros.  \n"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    assert run(model, (bev_tool,), question=PEACH_Q).reply == "Two cambros."


def test_route_decision_type_is_the_flows_route(run, Scripted, bev_tool):
    """Covers: AC-2 (right), EC-4. trace.route is a RouteDecision."""
    out = run(Scripted(["ok"]), (bev_tool,))
    assert isinstance(out.route, RouteDecision)

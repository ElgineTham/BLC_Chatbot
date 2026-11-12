"""AC-2: the chat flow (EC-4 to EC-13). Router, then tool steps, then the final call.

Unit tests with a scripted fake model: llm.invoke replies come from `plain` (router first, final last),
bound.invoke replies from `bound`. The real calculate_bev_item runs on the Appendix A catalog through
make_bev_tool(catalog); no Ollama, no network, nothing read under data/ (NFR-2).
"""

from __future__ import annotations

import dataclasses

import pytest
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, ToolMessage

import chat
from blc.router import RouteDecision, RoutedPart
from blc.tools.bev_tools import BEV_TOOL_NAME

DOC_MARK = "Coffee is under the coffee machine zzdocmarker."
DOCS = [Document(page_content=DOC_MARK, metadata={"source": "menu.md"})]
HISTORY = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]
QUESTION = "original user question quokka"
PEACH_Q = "How many cambros for 6 gallons of peach tea?"
CUPS_Q = "How many cold cups for 45 guests?"
VALID_CAMBROS = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}
VALID_CUPS = {"item": "cups", "drinks": ["lemonade"], "guests": 45}
INVALID = {"item": "pans"}


def run(model, tools, docs=None, history=None, question=QUESTION):
    return chat.answer_with_tools(
        model,
        HISTORY if history is None else history,
        DOCS if docs is None else docs,
        question,
        tools=tools,
    )


def tool_messages(messages):
    return [m for m in messages if isinstance(m, ToolMessage)]


def final_text(model, text_of):
    return text_of(model.plain_invocations[-1])


# ---------------------------------------------------------------- constants and records

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


def test_part_result_and_tool_answer_are_frozen_dataclasses():
    """Covers: AC-2 (right). PartResult and ToolAnswer have the contract fields and are frozen."""
    part = RoutedPart("DOCS", "q")
    pr = chat.PartResult(part, (), None)
    decision = RouteDecision((part,), "DOCS", False)
    ans = chat.ToolAnswer("reply", (), False, decision, (pr,))
    assert (pr.part, pr.tool_calls, pr.tool_text) == (part, (), None)
    assert (ans.reply, ans.tool_calls, ans.retried, ans.route, ans.parts) == ("reply", (), False, decision, (pr,))
    with pytest.raises(dataclasses.FrozenInstanceError):
        pr.tool_text = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        ans.reply = "x"


# ---------------------------------------------------------------- EC-4 DOCS only

def test_ec4_docs_only(Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. DOCS route: no bind_tools, 2 llm.invoke calls, docs in the final messages, no tool call."""
    model = Scripted(["DOCS: Where is the coffee?", "  Under the machine.  \n"])
    out = run(model, (bev_tool,))
    assert isinstance(out, chat.ToolAnswer)
    assert out.reply == "Under the machine."
    assert model.bind_calls == []
    assert len(model.plain_invocations) == 2
    assert model.bound_invocations == []
    assert out.tool_calls == ()
    assert out.retried is False
    assert out.route.kind == "DOCS"
    assert out.route.fallback is False
    assert len(out.parts) == 1
    assert out.parts[0].part == RoutedPart("DOCS", "Where is the coffee?")
    assert out.parts[0].tool_calls == ()
    assert out.parts[0].tool_text is None
    final = model.plain_invocations[-1]
    assert DOC_MARK in text_of(final)
    assert not tool_messages(final)


def test_ec4_final_call_shape(Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. Final messages: SystemMessage(ANSWER_PROMPT), the history, then the original question."""
    model = Scripted(["DOCS: Where is the coffee?", "Under the machine."])
    run(model, (bev_tool,))
    final = model.plain_invocations[-1]
    assert isinstance(final[0], SystemMessage)
    assert chat.ANSWER_PROMPT in final[0].content
    body = text_of(final)
    assert "earlier question zebra" in body and "earlier answer giraffe" in body
    assert QUESTION in body
    assert body.index("earlier question zebra") < body.index(QUESTION)
    assert str(final[-1].content).count(QUESTION) >= 1  # the question is in the last (human) message


def test_ec4_router_call_is_first_and_sees_question_and_history(Scripted, bev_tool, text_of):
    """Covers: AC-2 (right), EC-4. The first llm.invoke is the router call: it holds the question and history but no documents."""
    model = Scripted(["DOCS: Where is the coffee?", "Under the machine."])
    run(model, (bev_tool,))
    first = text_of(model.plain_invocations[0])
    assert QUESTION in first
    assert "earlier question zebra" in first
    assert DOC_MARK not in first
    assert chat.ANSWER_PROMPT not in first


# ---------------------------------------------------------------- EC-5 TOOL only

def test_ec5_tool_only(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-5. One tool step: the real tool runs once; the final messages hold its result and no documents."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Bring two cambros."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "id-5")])],
    )
    out = run(model, (bev_tool,))
    assert out.reply == "Bring two cambros."
    assert len(out.tool_calls) == 1
    rec = out.tool_calls[0]
    assert (rec.name, rec.args) == (BEV_TOOL_NAME, VALID_CAMBROS)
    assert not rec.result.strip().lower().startswith(("invalid", "error"))
    assert out.parts[0].tool_text == rec.result
    assert out.parts[0].tool_calls == (rec,)
    assert out.route.kind == "TOOL"
    assert out.retried is False
    assert len(model.bind_calls) == 1 and model.bind_calls[0] == [bev_tool]
    assert len(model.bound_invocations) == 1
    assert len(model.plain_invocations) == 2
    final = final_text(model, text_of)
    assert rec.result in final
    assert DOC_MARK not in final
    assert QUESTION in final


def test_ec5_tool_step_messages_have_no_documents_and_no_history(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-5. The tool step gets TOOL_PROMPT and the part's text only: no document text, no history, no original question."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    run(model, (bev_tool,))
    step = model.bound_invocations[0]
    assert isinstance(step[0], SystemMessage)
    assert chat.TOOL_PROMPT in step[0].content
    body = text_of(step)
    assert PEACH_Q in body
    assert DOC_MARK not in body
    assert "zebra" not in body and "giraffe" not in body
    assert QUESTION not in body
    assert chat.ANSWER_PROMPT not in body


def test_ec5_final_call_has_no_tool_bound_and_is_plain_invoke(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-5, spec 4.5. The tool is bound once for the tool step; the final call is a plain llm.invoke (the last one)."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    run(model, (bev_tool,))
    assert len(model.bind_calls) == 1
    assert len(model.plain_invocations) == 2
    assert model.plain_script == [] and model.bound_script == []


def test_ec5_final_message_labels_the_tool_part_question(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-5, spec 4.5. The final human message carries the TOOL part's question next to its result."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    out = run(model, (bev_tool,))
    last = str(model.plain_invocations[-1][-1].content)
    assert PEACH_Q in last
    assert out.tool_calls[0].result in last


def test_ec5_tool_message_id_not_needed_when_step_ends_after_valid_round(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-5. A valid first round ends the step: the model is not asked again (script of one reply suffices)."""
    model = Scripted(["TOOL: " + PEACH_Q, "Done."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    run(model, (bev_tool,))
    assert len(model.bound_invocations) == 1


# ---------------------------------------------------------------- EC-6 BOTH

def test_ec6_both(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-6. DOCS then TOOL: one tool step for the TOOL part; the final messages hold the docs and the tool result."""
    model = Scripted(
        ["DOCS: Where are lemons kept?\nTOOL: " + CUPS_Q, "Lemons are kept ... and bring cups."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    out = run(model, (bev_tool,))
    assert out.route.kind == "BOTH"
    assert len(out.parts) == 2
    docs_part, tool_part = out.parts
    assert docs_part.part == RoutedPart("DOCS", "Where are lemons kept?")
    assert docs_part.tool_text is None and docs_part.tool_calls == ()
    assert tool_part.part == RoutedPart("TOOL", CUPS_Q)
    assert tool_part.tool_text == out.tool_calls[0].result
    assert len(out.tool_calls) == 1
    assert len(model.bound_invocations) == 1
    assert CUPS_Q in text_of(model.bound_invocations[0])
    assert "Where are lemons kept?" not in text_of(model.bound_invocations[0])
    final = final_text(model, text_of)
    assert DOC_MARK in final
    assert tool_part.tool_text in final
    assert out.reply == "Lemons are kept ... and bring cups."


def test_ec6_both_tool_first(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-6. TOOL then DOCS: parts keep the router's order."""
    model = Scripted(
        ["TOOL: " + CUPS_Q + "\nDOCS: Where are lemons kept?", "ok"],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    out = run(model, (bev_tool,))
    assert [p.part.route for p in out.parts] == ["TOOL", "DOCS"]
    assert out.parts[0].tool_text is not None and out.parts[1].tool_text is None


# ---------------------------------------------------------------- EC-7 two TOOL parts

def test_ec7_two_tool_parts(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (right), EC-7. Two tool steps in order; tool_calls lists both calls in order; the tool is bound once."""
    model = Scripted(
        ["TOOL: " + PEACH_Q + "\nTOOL: " + CUPS_Q, "Both done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "a")]), ai("", [tc(BEV_TOOL_NAME, VALID_CUPS, "b")])],
    )
    out = run(model, (bev_tool,))
    assert out.route.kind == "TOOL"
    assert [r.args for r in out.tool_calls] == [VALID_CAMBROS, VALID_CUPS]
    assert len(out.parts) == 2
    assert out.parts[0].tool_calls == (out.tool_calls[0],)
    assert out.parts[1].tool_calls == (out.tool_calls[1],)
    assert out.parts[0].tool_text == out.tool_calls[0].result
    assert out.parts[1].tool_text == out.tool_calls[1].result
    assert len(model.bind_calls) == 1
    assert len(model.bound_invocations) == 2
    assert PEACH_Q in text_of(model.bound_invocations[0]) and CUPS_Q not in text_of(model.bound_invocations[0])
    assert CUPS_Q in text_of(model.bound_invocations[1]) and PEACH_Q not in text_of(model.bound_invocations[1])
    final = final_text(model, text_of)
    assert out.parts[0].tool_text in final and out.parts[1].tool_text in final
    assert DOC_MARK not in final
    assert len(model.plain_invocations) == 2


# ---------------------------------------------------------------- EC-8 / EC-9 rounds

def test_ec8_invalid_then_fixed(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-8. First result starts with 'invalid'; the model is asked again; tool_text is the second result."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Fixed answer."],
        bound=[ai("", [tc(BEV_TOOL_NAME, INVALID, "bad")]), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "good")])],
    )
    out = run(model, (bev_tool,))
    assert len(model.bound_invocations) == 2
    assert len(out.tool_calls) == 2
    first, second = out.tool_calls
    assert first.result.strip().lower().startswith("invalid")
    assert not second.result.strip().lower().startswith(("invalid", "error"))
    assert out.parts[0].tool_text == second.result
    assert out.parts[0].tool_calls == out.tool_calls
    assert out.reply == "Fixed answer."
    tms = tool_messages(model.bound_invocations[1])
    assert len(tms) == 1
    assert tms[0].tool_call_id == "bad"
    assert tms[0].content == first.result


def test_ec9_never_valid_hits_round_limit(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (wrong, boundary), EC-9. Invalid calls forever: after MAX_TOOL_ROUNDS rounds tool_text is TOOL_LIMIT_REPLY."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Sorry."],
        bound=[ai("", [tc(BEV_TOOL_NAME, INVALID, "x")])],
        repeat_last=True,
    )
    out = run(model, (bev_tool,))
    assert len(model.bound_invocations) == chat.MAX_TOOL_ROUNDS
    assert len(out.tool_calls) == chat.MAX_TOOL_ROUNDS
    assert out.parts[0].tool_text == chat.TOOL_LIMIT_REPLY
    assert out.retried is False
    assert len(model.plain_invocations) == 2  # the final call still happens, once


def test_ec9_valid_on_last_allowed_round(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-9. Valid on round MAX_TOOL_ROUNDS is accepted, not the limit reply."""
    bound = [ai("", [tc(BEV_TOOL_NAME, INVALID, f"i{n}")]) for n in range(chat.MAX_TOOL_ROUNDS - 1)]
    bound.append(ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "ok")]))
    model = Scripted(["TOOL: " + PEACH_Q, "Done."], bound=bound)
    out = run(model, (bev_tool,))
    assert len(model.bound_invocations) == chat.MAX_TOOL_ROUNDS
    assert out.parts[0].tool_text == out.tool_calls[-1].result != chat.TOOL_LIMIT_REPLY


def test_round_with_two_valid_calls_joins_results_with_newline(Scripted, ai, tc, make_tool):
    """Covers: AC-2 (boundary), spec 4.3. Several valid calls in one round: tool_text is the results joined with a newline, in call order."""
    t, calls = make_tool(BEV_TOOL_NAME, result="R-ONE")
    model = Scripted(
        ["TOOL: " + PEACH_Q, "ok"],
        bound=[ai("", [tc(BEV_TOOL_NAME, {"x": "1"}, "a"), tc(BEV_TOOL_NAME, {"x": "2"}, "b")])],
    )
    out = run(model, (t,))
    assert calls == [{"x": "1"}, {"x": "2"}]
    assert len(out.tool_calls) == 2
    assert out.parts[0].tool_text == "R-ONE\nR-ONE"
    assert len(model.bound_invocations) == 1


# ---------------------------------------------------------------- EC-10 no call

def test_ec10_no_call_then_call(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (right), EC-10. No call first, a call after the reminder: retried=True and the tool runs."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Done."],
        bound=[ai("I think two cambros."), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])],
    )
    out = run(model, (bev_tool,))
    assert out.retried is True
    assert len(model.bound_invocations) == 2
    assert len(model.bound_invocations[1]) > len(model.bound_invocations[0])  # a reminder was added
    assert len(out.tool_calls) == 1
    assert out.parts[0].tool_text == out.tool_calls[0].result


def test_ec10_no_call_twice_falls_back_to_docs(Scripted, ai, bev_tool, text_of):
    """Covers: AC-2 (wrong), EC-10. No call twice: tool_text None, no calls, the final messages contain the docs."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "I don't know."],
        bound=[ai("Two cambros."), ai("Still two cambros.")],
    )
    out = run(model, (bev_tool,))
    assert out.retried is True
    assert len(model.bound_invocations) == 2  # asked exactly twice, no third time
    assert out.tool_calls == ()
    assert out.parts[0].part.route == "TOOL"
    assert out.parts[0].tool_text is None
    assert out.parts[0].tool_calls == ()
    final = final_text(model, text_of)
    assert DOC_MARK in final
    assert out.reply == "I don't know."


def test_ec10_fallen_back_part_next_to_working_tool_part(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-2 (boundary), EC-10. A fallen-back TOOL part does not stop a later TOOL part; docs and the later result both reach the final call."""
    model = Scripted(
        ["TOOL: " + PEACH_Q + "\nTOOL: " + CUPS_Q, "ok"],
        bound=[ai("no"), ai("still no"), ai("", [tc(BEV_TOOL_NAME, VALID_CUPS)])],
    )
    out = run(model, (bev_tool,))
    assert out.parts[0].tool_text is None
    assert out.parts[1].tool_text == out.tool_calls[0].result
    assert len(out.tool_calls) == 1
    final = final_text(model, text_of)
    assert DOC_MARK in final
    assert out.parts[1].tool_text in final


def test_ec10_no_call_on_valid_first_try_is_not_retried(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (wrong), EC-10. A tool call on the first reply never sets retried."""
    model = Scripted(["TOOL: " + PEACH_Q, "ok"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    assert run(model, (bev_tool,)).retried is False


# ---------------------------------------------------------------- EC-11 router fallback

def test_ec11_router_fallback_behaves_like_docs(Scripted, bev_tool, text_of):
    """Covers: AC-2 (wrong), EC-11. An unlabelled router reply: one DOCS part with the whole question, fallback=True, no tool."""
    model = Scripted(["I think this is a tool question.", "Under the machine."])
    out = run(model, (bev_tool,))
    assert out.route.fallback is True
    assert out.route.kind == "DOCS"
    assert out.route.parts == (RoutedPart("DOCS", QUESTION),)
    assert model.bind_calls == []
    assert len(model.plain_invocations) == 2
    assert out.tool_calls == ()
    assert DOC_MARK in final_text(model, text_of)
    assert out.reply == "Under the machine."


# ---------------------------------------------------------------- EC-12 unknown tool

def test_ec12_unknown_tool_name(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (wrong), EC-12. An unknown tool name gives 'error: unknown tool <name>', is recorded and sent back, and the next round runs."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Done."],
        bound=[ai("", [tc("made_up_tool", {"q": 1}, "u1")]), ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS, "g1")])],
    )
    out = run(model, (bev_tool,))
    assert out.tool_calls[0] == chat.ToolCallRecord("made_up_tool", {"q": 1}, "error: unknown tool made_up_tool")
    tms = tool_messages(model.bound_invocations[1])
    assert tms[0].tool_call_id == "u1"
    assert tms[0].content == "error: unknown tool made_up_tool"
    assert len(out.tool_calls) == 2
    assert out.parts[0].tool_text == out.tool_calls[1].result


def test_ec12_unknown_tool_forever_hits_limit(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), EC-12, EC-9. 'error...' results count as failed rounds: after MAX_TOOL_ROUNDS rounds tool_text is TOOL_LIMIT_REPLY."""
    model = Scripted(
        ["TOOL: " + PEACH_Q, "Sorry."],
        bound=[ai("", [tc("nope", {}, "n")])],
        repeat_last=True,
    )
    out = run(model, (bev_tool,))
    assert len(model.bound_invocations) == chat.MAX_TOOL_ROUNDS
    assert out.parts[0].tool_text == chat.TOOL_LIMIT_REPLY
    assert all(r.result == "error: unknown tool nope" for r in out.tool_calls)


# ---------------------------------------------------------------- EC-13 answer_from_context and printing

def test_ec13_answer_from_context_returns_reply(Scripted):
    """Covers: AC-2 (right), EC-13. answer_from_context equals answer_with_tools(...).reply (DOCS route, so no tool and no data/ access)."""
    def model():
        return Scripted(["DOCS: Where is the coffee?", "Under the machine."])

    expected = chat.answer_with_tools(model(), HISTORY, DOCS, QUESTION).reply
    got = chat.answer_from_context(model(), HISTORY, DOCS, QUESTION)
    assert isinstance(got, str)
    assert got == expected == "Under the machine."


def test_ec13_answer_from_context_delegates(monkeypatch):
    """Covers: AC-2 (right), EC-13. answer_from_context passes its arguments on and returns only .reply."""
    seen = {}
    decision = RouteDecision((RoutedPart("DOCS", "q"),), "DOCS", False)

    def fake_awt(llm, history, docs, question, *args, **kwargs):
        seen["args"] = (llm, history, docs, question)
        return chat.ToolAnswer("THE-REPLY", (), False, decision, ())

    monkeypatch.setattr(chat, "answer_with_tools", fake_awt)
    marker = object()
    assert chat.answer_from_context(marker, HISTORY, DOCS, "Q?") == "THE-REPLY"
    assert seen["args"] == (marker, HISTORY, DOCS, "Q?")


def test_ec13_nothing_printed_and_history_untouched(Scripted, ai, tc, bev_tool, capsys):
    """Covers: AC-2 (boundary), EC-13. A full TOOL answer prints nothing and does not change the history list."""
    history = [dict(m) for m in HISTORY]
    model = Scripted(["TOOL: " + PEACH_Q, "ok"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    run(model, (bev_tool,), history=history)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert history == HISTORY


def test_reply_is_stripped_of_surrounding_whitespace(Scripted, ai, tc, bev_tool):
    """Covers: AC-2 (boundary), spec 4.5. The reply is the final call's content, stripped."""
    model = Scripted(["TOOL: " + PEACH_Q, "\n  Two cambros.  \n"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID_CAMBROS)])])
    assert run(model, (bev_tool,)).reply == "Two cambros."

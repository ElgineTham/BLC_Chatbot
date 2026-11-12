"""AC-4 (spec 010): the chat flow with route_faithfully (EC-14, EC-15).

Unit tests with the scripted fake model of conftest.py (Scripted): llm.invoke replies come from `plain`
(router reply or replies first, final reply last), bound.invoke replies from `bound`. No Ollama, no network.

Note: the existing flow tests in test_answer_flow.py all pass a non-empty history with a question that has no
number, menu drink or pull sheet item, so every scripted router reply there is already faithful by rule P
(nothing can be lost). They are left unchanged.
"""

from __future__ import annotations

import chat
from blc.router import RoutedPart
from blc.tools.bev_tools import BEV_TOOL_NAME

QUESTION = "How many cambros for 6 gallons of peach tea?"
VALID = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}
REWRITE = "TOOL: How many 5 gallon cambros do I need for six gallons of peach tea?"
DOC_MARK = "Peach tea is in the cooler zzdocmarker."


def _docs():
    from langchain_core.documents import Document

    return [Document(page_content=DOC_MARK, metadata={"source": "m.md"})]


def run(model, tools, history=None, question=QUESTION):
    return chat.answer_with_tools(model, [] if history is None else history, _docs(), question, tools=tools)


def test_ec14_unfaithful_twice_sends_whole_question_to_tool_step_and_final(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-4 (wrong), EC-14. Router unfaithful twice: the tool step and the final call get the whole question; route.unfaithful is True; 2 router calls then 1 final call."""
    model = Scripted(
        [REWRITE, REWRITE, "Two cambros."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID, "c1")])],
    )
    out = run(model, (bev_tool,))
    assert out.route.unfaithful is True
    assert out.route.fallback is False
    assert out.route.parts == (RoutedPart("TOOL", QUESTION),)
    assert out.parts[0].part == RoutedPart("TOOL", QUESTION)
    assert len(model.plain_invocations) == 3  # router, router retry, final
    assert len(model.bound_invocations) == 1
    step = text_of(model.bound_invocations[0])
    assert QUESTION in step
    assert "six gallons" not in step
    final = model.plain_invocations[-1]
    assert QUESTION in str(final[-1].content)
    assert out.tool_calls[0].result in text_of(final)
    assert out.reply == "Two cambros."


def test_ec14_retry_call_is_the_second_plain_call_and_final_is_last(Scripted, ai, tc, bev_tool, text_of):
    """Covers: AC-4 (wrong), EC-14. The second plain call is the router retry (holds the reason); the last holds the tool result and the answer prompt."""
    model = Scripted([REWRITE, REWRITE, "ok"], bound=[ai("", [tc(BEV_TOOL_NAME, VALID)])])
    run(model, (bev_tool,))
    assert chat.ANSWER_PROMPT not in text_of(model.plain_invocations[0])
    assert chat.ANSWER_PROMPT not in text_of(model.plain_invocations[1])
    assert "invalid (rewrite): " in text_of(model.plain_invocations[1])
    assert chat.ANSWER_PROMPT in text_of(model.plain_invocations[2])


def test_ec14_unfaithful_docs_only_uses_whole_question_as_docs(Scripted, bev_tool, text_of):  # noqa: E501
    """Covers: AC-4 (wrong), EC-14. Unfaithful DOCS replies give one DOCS part of the whole question; no tool step; docs reach the final call."""
    bad = "DOCS: Where do we keep the peach tea cooler?"
    model = Scripted([bad, bad, "In the cooler."])
    out = run(model, (bev_tool,), question="Where is the peach tea?")
    assert out.route.unfaithful is True
    assert out.route.parts == (RoutedPart("DOCS", "Where is the peach tea?"),)
    assert model.bind_calls == []
    assert len(model.plain_invocations) == 3
    assert DOC_MARK in text_of(model.plain_invocations[-1])


def test_ec14_second_reply_faithful_costs_two_router_calls(Scripted, ai, tc, bev_tool):
    """Covers: AC-4 (right), EC-14. First reply unfaithful, second faithful: the second decision is used, unfaithful False, three plain calls."""
    model = Scripted(
        [REWRITE, "TOOL: " + QUESTION, "Done."],
        bound=[ai("", [tc(BEV_TOOL_NAME, VALID)])],
    )
    out = run(model, (bev_tool,))
    assert out.route.unfaithful is False
    assert out.route.parts == (RoutedPart("TOOL", QUESTION),)
    assert len(model.plain_invocations) == 3


def test_ec15_faithful_first_reply_makes_one_router_call(Scripted, ai, tc, bev_tool):
    """Covers: AC-4 (right), EC-15. A faithful first reply: one router call, one tool step, one final call; unfaithful False."""
    model = Scripted(["TOOL: " + QUESTION, "Two cambros."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID)])])
    out = run(model, (bev_tool,))
    assert out.route.unfaithful is False
    assert len(model.plain_invocations) == 2
    assert len(model.bound_invocations) == 1
    assert len(model.bind_calls) == 1
    assert out.reply == "Two cambros."


def test_ec15_docs_only_faithful_makes_two_calls_and_no_bind(Scripted, bev_tool):
    """Covers: AC-4 (right), EC-15. A faithful DOCS reply: 2 llm.invoke calls and no bind_tools call."""
    model = Scripted(["DOCS: Where is the peach tea?", "In the cooler."])
    out = run(model, (bev_tool,), question="Where is the peach tea?")
    assert len(model.plain_invocations) == 2
    assert model.bind_calls == []
    assert out.route.unfaithful is False


def test_ec15_unreadable_router_reply_is_not_retried(Scripted, bev_tool):
    """Covers: AC-4 (wrong), EC-15. An unreadable first reply is not retried: 2 plain calls in all; fallback True, unfaithful False."""
    model = Scripted(["garbage", "In the cooler."])
    out = run(model, (bev_tool,))
    assert out.route.fallback is True and out.route.unfaithful is False
    assert len(model.plain_invocations) == 2


def test_followup_with_history_rewrite_keeping_numbers_is_accepted(Scripted, ai, tc, bev_tool):
    """Covers: AC-4 (right), EC-15. With history, a rewrite that keeps the number and adds the item passes at once (one router call)."""
    history = [
        {"role": "user", "content": "How many cambros for peach tea?"},
        {"role": "assistant", "content": "How many gallons?"},
    ]
    model = Scripted(["TOOL: How many cambros for 6 gallons of peach tea?", "Done."], bound=[ai("", [tc(BEV_TOOL_NAME, VALID)])])
    out = run(model, (bev_tool,), history=history, question="6 gallons.")
    assert out.route.unfaithful is False
    assert len(model.plain_invocations) == 2

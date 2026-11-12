"""AC-3 (spec 010): route_faithfully (section 4.2, EC-9 to EC-13) and the RouteDecision.unfaithful field.

Unit tests with a scripted fake model that has only invoke and records every call. No Ollama, no network.
"""

from __future__ import annotations

import dataclasses

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from blc.router import (
    ROUTER_SCHEMA,
    RouteDecision,
    RoutedPart,
    check_fidelity,
    route_faithfully,
    route_question,
)

Q = "I need 9 gallons of decaf and hot water, how many containers?"
GOOD = ("TOOL", Q)
SPLIT = (
    ("TOOL", "How many containers for 9 gallons of decaf?"),
    ("TOOL", "How many containers for 9 gallons of hot water?"),
)
MIXED_BAD = (("DOCS", "Where is the decaf kept?"), ("TOOL", "How many containers for 9 gallons?"))
HISTORY = [
    {"role": "user", "content": "How many cambros for orange juice and iced tea?"},
    {"role": "assistant", "content": "How many gallons of each?"},
]


def run(fake, question=Q, history=None):
    return route_faithfully(fake, [] if history is None else history, question)


def sig(messages):
    return [(type(m), m.content) for m in messages]


def whole(route, question=Q):
    return (RoutedPart(route, question),)


# ---------------------------------------------------------------- RouteDecision field

def test_route_decision_unfaithful_defaults_to_false():
    """Covers: AC-3 (right), section 3.2. Building RouteDecision with three arguments still works; unfaithful is False."""
    d = RouteDecision((RoutedPart("DOCS", "q"),), "DOCS", False)
    assert d.unfaithful is False


def test_route_decision_unfaithful_can_be_set_and_is_frozen():
    """Covers: AC-3 (right, wrong), section 3.2. unfaithful can be given; the record is frozen."""
    d = RouteDecision((RoutedPart("DOCS", "q"),), "DOCS", False, True)
    assert d.unfaithful is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.unfaithful = False


# ---------------------------------------------------------------- EC-9: the table

def test_first_reply_faithful_one_call(RouterFake, jparts):
    """Covers: AC-3 (right), EC-9. A faithful first reply: one invoke, the first decision, unfaithful False."""
    fake = RouterFake(jparts(GOOD))
    d = run(fake)
    assert len(fake.messages) == 1
    assert d.parts == whole("TOOL")
    assert (d.kind, d.fallback, d.unfaithful) == ("TOOL", False, False)
    assert fake.script == []


def test_first_unfaithful_second_faithful_two_calls(RouterFake, jparts):
    """Covers: AC-3 (right), EC-9. Unfaithful first, faithful second: two invokes, the second decision, unfaithful False."""
    fake = RouterFake(jparts(*SPLIT), jparts(GOOD))
    d = run(fake)
    assert len(fake.messages) == 2
    assert d.parts == whole("TOOL")
    assert (d.kind, d.fallback, d.unfaithful) == ("TOOL", False, False)


def test_second_call_last_message_contains_the_reason(RouterFake, jparts):
    """Covers: AC-3 (right), EC-9. The second call's last message holds the reason from check_fidelity for the first reply."""
    fake = RouterFake(jparts(*SPLIT), jparts(GOOD))
    run(fake)
    reason = check_fidelity(Q, [], tuple(RoutedPart(r, t) for r, t in SPLIT))
    assert reason
    assert reason in str(fake.messages[1][-1].content)


def test_both_unfaithful_all_tool_gives_whole_question_tool(RouterFake, jparts):
    """Covers: AC-3 (wrong), EC-9. Both replies unfaithful and all TOOL: (TOOL, whole question), unfaithful True, fallback False."""
    fake = RouterFake(jparts(*SPLIT), jparts(*SPLIT))
    d = run(fake)
    assert len(fake.messages) == 2
    assert d.parts == whole("TOOL")
    assert (d.kind, d.fallback, d.unfaithful) == ("TOOL", False, True)


def test_both_unfaithful_mixed_gives_whole_question_docs(RouterFake, jparts):
    """Covers: AC-3 (wrong), EC-9. Both unfaithful and mixed: (DOCS, whole question), unfaithful True."""
    fake = RouterFake(jparts(*MIXED_BAD), jparts(*MIXED_BAD))
    d = run(fake)
    assert len(fake.messages) == 2
    assert d.parts == whole("DOCS")
    assert (d.kind, d.fallback, d.unfaithful) == ("DOCS", False, True)


def test_both_unfaithful_docs_only_gives_whole_question_docs(RouterFake, jparts):
    """Covers: AC-3 (wrong), EC-9. Both unfaithful and DOCS: (DOCS, whole question), unfaithful True."""
    bad = (("DOCS", "Where is the decaf kept?"),)
    d = run(RouterFake(jparts(*bad), jparts(*bad)))
    assert d.parts == whole("DOCS")
    assert d.unfaithful is True and d.fallback is False


def test_route_comes_from_the_latest_readable_decision(RouterFake, jparts):
    """Covers: AC-3 (boundary), EC-9. First mixed, second all TOOL: the fallback is TOOL. First all TOOL, second mixed: DOCS."""
    d1 = run(RouterFake(jparts(*MIXED_BAD), jparts(*SPLIT)))
    assert d1.parts == whole("TOOL") and d1.unfaithful is True
    d2 = run(RouterFake(jparts(*SPLIT), jparts(*MIXED_BAD)))
    assert d2.parts == whole("DOCS") and d2.unfaithful is True


@pytest.mark.parametrize("bad_second", ["garbage", "", "{}", '{"parts": []}'])
def test_first_unfaithful_second_unreadable_all_tool(RouterFake, jparts, bad_second):
    """Covers: AC-3 (wrong), EC-9. Second reply unreadable: whole-question fallback; route from the first decision (TOOL)."""
    fake = RouterFake(jparts(*SPLIT), bad_second)
    d = run(fake)
    assert len(fake.messages) == 2
    assert d.parts == whole("TOOL")
    assert (d.kind, d.fallback, d.unfaithful) == ("TOOL", False, True)


def test_first_unfaithful_second_unreadable_mixed_gives_docs(RouterFake, jparts):
    """Covers: AC-3 (wrong), EC-9. Second unreadable, first mixed: DOCS whole question."""
    d = run(RouterFake(jparts(*MIXED_BAD), "garbage"))
    assert d.parts == whole("DOCS")
    assert d.unfaithful is True and d.fallback is False


@pytest.mark.parametrize("reply", ["garbage", "I think this is a tool question.", ""])
def test_first_reply_unreadable_one_call_docs_fallback(RouterFake, reply):
    """Covers: AC-3 (wrong), EC-9. Unreadable first reply: one invoke, DOCS fallback with fallback True, unfaithful False."""
    fake = RouterFake(reply)
    d = run(fake)
    assert len(fake.messages) == 1
    assert d.parts == whole("DOCS")
    assert (d.kind, d.fallback, d.unfaithful) == ("DOCS", True, False)


def test_unreadable_first_reply_matches_route_question(RouterFake):
    """Covers: AC-3 (right), EC-9, EC-13. The unreadable-first-reply decision equals route_question's."""
    assert run(RouterFake("garbage")) == route_question(RouterFake("garbage"), [], Q)


def test_whole_question_text_is_stripped(RouterFake, jparts):
    """Covers: AC-3 (boundary), EC-9. The fallback part's text is the stripped question."""
    q = "  " + Q + " \n"
    d = run(RouterFake(jparts(*SPLIT), jparts(*SPLIT)), question=q)
    assert d.parts == whole("TOOL", Q)


def test_item_less_question_makes_whole_question_docs(RouterFake, jparts):
    """Covers: AC-3 (boundary), EC-9. All TOOL but the question has no pull sheet item: the fallback route is DOCS."""
    q = "Where is the mint kept for tea?"
    bad = (("TOOL", "How many cups for the mint?"),)
    d = run(RouterFake(jparts(*bad), jparts(*bad)), question=q)
    assert d.parts == whole("DOCS", q)
    assert (d.kind, d.fallback, d.unfaithful) == ("DOCS", False, True)


# ---------------------------------------------------------------- EC-10: call shape

def test_every_call_has_only_the_format_keyword(RouterFake, jparts):
    """Covers: AC-3 (right), EC-10. Both invokes carry exactly format=ROUTER_SCHEMA and no positional extras."""
    fake = RouterFake(jparts(*SPLIT), jparts(*SPLIT))
    run(fake)
    assert fake.kwargs == [{"format": ROUTER_SCHEMA}, {"format": ROUTER_SCHEMA}]
    assert fake.args == [(), ()]


def test_single_call_has_only_the_format_keyword(RouterFake, jparts):
    """Covers: AC-3 (right), EC-10. The one call of a faithful reply carries format only."""
    fake = RouterFake(jparts(GOOD))
    run(fake)
    assert fake.kwargs == [{"format": ROUTER_SCHEMA}]


def test_fake_without_bind_methods_works(RouterFake, jparts):
    """Covers: AC-3 (right), EC-10. A model with only invoke is enough (no bind, bind_tools or with_structured_output)."""
    fake = RouterFake(jparts(*SPLIT), jparts(GOOD))
    assert not any(hasattr(fake, n) for n in ("bind", "bind_tools", "with_structured_output"))
    assert run(fake).kind == "TOOL"


def test_second_call_messages_are_first_messages_reply_and_one_human_message(RouterFake, jparts):
    """Covers: AC-3 (right), EC-10. Second messages: the first call's messages, the first reply as an assistant message, one human message with the reason."""
    first_reply = jparts(*SPLIT)
    fake = RouterFake(first_reply, jparts(GOOD))
    run(fake)
    first, second = fake.messages
    assert len(second) == len(first) + 2
    assert sig(second[: len(first)]) == sig(first)
    assert isinstance(second[-2], AIMessage)
    assert second[-2].content == first_reply
    assert isinstance(second[-1], HumanMessage)
    reason = check_fidelity(Q, [], tuple(RoutedPart(r, t) for r, t in SPLIT))
    assert reason in second[-1].content


def test_first_call_messages_equal_route_question_messages(RouterFake, jparts):
    """Covers: AC-3 (right), EC-10. The first call is made exactly as route_question makes it: system prompt then one human message."""
    fake = RouterFake(jparts(GOOD))
    ref = RouterFake(jparts(GOOD))
    run(fake, history=HISTORY)
    route_question(ref, HISTORY, Q)
    assert sig(fake.messages[0]) == sig(ref.messages[0])
    assert isinstance(fake.messages[0][0], SystemMessage)


def test_retry_with_history_uses_the_same_first_messages(RouterFake, jparts):
    """Covers: AC-3 (right), EC-10. With history, an unfaithful reply (lost number) is retried with the first messages plus two more."""
    lost = jparts(("TOOL", "How many cambros for 4 gallons of orange juice?"))
    fake = RouterFake(lost, jparts(("TOOL", "How many cambros for 6 gallons of orange juice and 6 gallons of iced tea?")))
    d = route_faithfully(fake, HISTORY, "6 each.")
    first, second = fake.messages
    assert len(second) == len(first) + 2
    assert sig(second[: len(first)]) == sig(first)
    assert "6" in second[-1].content
    assert d.unfaithful is False and d.fallback is False


# ---------------------------------------------------------------- EC-11: blank question

@pytest.mark.parametrize("question", ["", " ", "\n\t  "])
def test_blank_question_raises_before_any_call(RouterFake, jparts, question):
    """Covers: AC-3 (wrong, boundary), EC-11. A blank question raises ValueError and the model is never invoked."""
    fake = RouterFake(jparts(GOOD))
    with pytest.raises(ValueError):
        route_faithfully(fake, [], question)
    assert fake.messages == []


# ---------------------------------------------------------------- EC-12: the item guard still applies

def test_guard_applies_before_the_check(RouterFake, jparts):
    """Covers: AC-3 (right), EC-12. A TOOL part with no item becomes DOCS before the check; a verbatim reply is faithful in one call."""
    q = "Where is the mint kept? How many cups for 45 guests?"
    fake = RouterFake(jparts(("TOOL", "Where is the mint kept?"), ("TOOL", "How many cups for 45 guests?")))
    d = run(fake, question=q)
    assert len(fake.messages) == 1
    assert [p.route for p in d.parts] == ["DOCS", "TOOL"]
    assert d.kind == "BOTH"
    assert d.unfaithful is False


def test_guard_makes_the_fallback_route_docs(RouterFake, jparts):
    """Covers: AC-3 (wrong), EC-12. After the guard the parts are mixed, so the whole-question fallback is DOCS."""
    q = "Where is the mint kept? How many cups for 45 guests?"
    bad = jparts(("TOOL", "Where is the mint kept now?"), ("TOOL", "How many cups for 45 guests?"))
    d = run(RouterFake(bad, bad), question=q)
    assert d.parts == whole("DOCS", q)
    assert d.unfaithful is True and d.kind == "DOCS"


def test_guard_applies_to_the_second_reply(RouterFake, jparts):
    """Covers: AC-3 (right), EC-12. The second reply is read with the guard too."""
    q = "Where is the mint kept? How many cups for 45 guests?"
    first = jparts(("TOOL", "Where is the mint kept now?"))
    second = jparts(("TOOL", "Where is the mint kept?"), ("TOOL", "How many cups for 45 guests?"))
    d = run(RouterFake(first, second), question=q)
    assert [p.route for p in d.parts] == ["DOCS", "TOOL"]
    assert d.unfaithful is False


def test_whole_question_with_items_stays_tool_after_guard_rule(RouterFake, jparts):
    """Covers: AC-3 (right), EC-12. All TOOL and the question has an item: the fallback is TOOL (not changed by the guard)."""
    d = run(RouterFake(jparts(*SPLIT), jparts(*SPLIT)))
    assert d.parts[0].route == "TOOL"


# ---------------------------------------------------------------- EC-13: equals route_question when faithful

@pytest.mark.parametrize(
    "question, history, reply_parts",
    [
        (Q, [], (GOOD,)),
        ("Where is the creamer kept, and do I bring sugar for hot water for 35 guests?", [],
         (("DOCS", "Where is the creamer kept?"), ("TOOL", "do I bring sugar for hot water for 35 guests?"))),
        ("Seven gallons of decaf, which containers?", HISTORY, (("TOOL", "Which containers hold 7 gallons of decaf?"),)),
        ("Where is the mint kept?", [], (("TOOL", "Where is the mint kept?"),)),
    ],
)
def test_faithful_decision_equals_route_question(RouterFake, jparts, question, history, reply_parts):
    """Covers: AC-3 (right), EC-13. For a faithful reply the decision equals route_question's for the same reply."""
    reply = jparts(*reply_parts)
    got = route_faithfully(RouterFake(reply), history, question)
    expected = route_question(RouterFake(reply), history, question)
    assert got == expected
    assert got.unfaithful is False


def test_label_line_reply_is_read_like_route_question(RouterFake):
    """Covers: AC-3 (right), EC-13 (extra). Label-line replies work through route_faithfully the same way."""
    q = "Where is the creamer kept? How many cups for 45 guests?"
    reply = "DOCS: Where is the creamer kept?\nTOOL: How many cups for 45 guests?"
    assert route_faithfully(RouterFake(reply), [], q) == route_question(RouterFake(reply), [], q)


# ---------------------------------------------------------------- extra

def test_prints_nothing_and_keeps_history(RouterFake, jparts, capsys):
    """Covers: AC-3 (boundary). Nothing is printed and the history list is unchanged."""
    history = [dict(m) for m in HISTORY]
    route_faithfully(RouterFake(jparts(*SPLIT), jparts(*SPLIT)), history, Q)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert history == HISTORY


def test_model_never_called_a_third_time(RouterFake, jparts):
    """Covers: AC-3 (boundary), EC-9. Two unfaithful replies end with two calls; a third reply is left unused."""
    fake = RouterFake(jparts(*SPLIT), jparts(*SPLIT), jparts(GOOD))
    d = run(fake)
    assert len(fake.messages) == 2
    assert len(fake.script) == 1
    assert d.unfaithful is True

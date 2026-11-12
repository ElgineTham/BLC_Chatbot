"""Spec 013 AC-3: route_fast (section 4.5, EC-18 to EC-25).

Unit tests with RouterFake from conftest.py: a scripted fake model that has only `invoke`, records every
call, and fails the test if it is invoked more often than scripted. No Ollama, no network, nothing read
under data/ (NFR-2).
"""

from __future__ import annotations

import copy
import dataclasses

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from blc.router import RouteDecision, RoutedPart, classifier_prompt, route_fast

BEV = "calculate_bev_item"
DOCS_Q = "Where is the coffee?"
TOOL_Q = "How many cambros do I need for 7 gallons of lemonade?"
BOTH_COMMA_Q = "Where is the coffee, and how many cups do I need for 55 guests?"
CREAMER_Q = "Where is the creamer kept, and how many cups do I need for 55 guests?"
TWO_TOOL_Q = "How many cups for 55 guests? Do I bring sugar for hot water?"
H_CAMBROS = [
    {"role": "user", "content": "How many cambros do I need for hot water and decaf?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]


def human_lines(fake, call=0):
    msgs = fake.messages[call]
    return str(msgs[-1].content).splitlines()


# ---------------------------------------------------------------- EC-18 table rows

def test_docs_question_makes_no_call(RouterFake):
    """Covers: AC-3 (right), EC-18. A standalone question with no number and no item word is DOCS without the model."""
    fake = RouterFake()
    d = route_fast(fake, [], DOCS_Q)
    assert isinstance(d, RouteDecision)
    assert d.parts == (RoutedPart("DOCS", DOCS_Q, None),)
    assert d.kind == "DOCS"
    assert d.fallback is False and d.unfaithful is False
    assert fake.messages == []


@pytest.mark.parametrize("reply", ["T", " Tool.", "tool", "t"])
def test_tool_question(RouterFake, reply):
    """Covers: AC-3 (right), EC-18. One part and a T reply: TOOL with the question as text and calculate_bev_item as tool."""
    fake = RouterFake(reply)
    d = route_fast(fake, [], TOOL_Q)
    assert d.parts == (RoutedPart("TOOL", TOOL_Q, BEV),)
    assert d.kind == "TOOL"
    assert d.fallback is False and d.unfaithful is False
    assert len(fake.messages) == 1


def test_both_only_second_part_is_sent(RouterFake):
    """Covers: AC-3 (right), EC-18. The quick DOCS part is not sent; one reply letter labels the second part."""
    fake = RouterFake("T")
    d = route_fast(fake, [], BOTH_COMMA_Q)
    assert d.parts == (
        RoutedPart("DOCS", "Where is the coffee", None),
        RoutedPart("TOOL", "how many cups do I need for 55 guests?", BEV),
    )
    assert d.kind == "BOTH"
    assert d.fallback is False
    assert human_lines(fake) == ["1. how many cups do I need for 55 guests?"]


@pytest.mark.parametrize("reply", ["DT", "D T", "DOCS TOOL"])
def test_both_parts_sent_when_both_have_item_words(RouterFake, reply):
    """Covers: AC-3 (right), EC-18. 'creamer' and 'cups' are item words, so both parts go to the model and DT labels them DOCS, TOOL."""
    fake = RouterFake(reply)
    d = route_fast(fake, [], CREAMER_Q)
    assert d.parts == (
        RoutedPart("DOCS", "Where is the creamer kept", None),
        RoutedPart("TOOL", "how many cups do I need for 55 guests?", BEV),
    )
    assert d.kind == "BOTH"
    assert d.fallback is False
    assert human_lines(fake) == [
        "1. Where is the creamer kept",
        "2. how many cups do I need for 55 guests?",
    ]


def test_numbering_counts_only_parts_sent_to_the_model(RouterFake):
    """Covers: AC-3 (boundary), EC-18, EC-20, section 4.5 step 3. A quick DOCS part in the middle is skipped and the numbering stays 1, 2 for the sent parts."""
    q = "Where is the coffee? How many cups for 5 guests? Where is the break room? How many cambros for 6 gallons?"
    fake = RouterFake("TT")
    d = route_fast(fake, [], q)
    assert human_lines(fake) == ["1. How many cups for 5 guests?", "2. How many cambros for 6 gallons?"]
    assert [p.route for p in d.parts] == ["DOCS", "TOOL", "DOCS", "TOOL"]
    assert [p.text for p in d.parts] == [
        "Where is the coffee?",
        "How many cups for 5 guests?",
        "Where is the break room?",
        "How many cambros for 6 gallons?",
    ]


def test_one_label_for_two_parts_falls_back(RouterFake):
    """Covers: AC-3 (wrong), EC-18. A single letter for two sent parts: fallback True and both parts DOCS."""
    d = route_fast(RouterFake("T"), [], CREAMER_Q)
    assert d.fallback is True
    assert d.kind == "DOCS"
    assert d.parts == (
        RoutedPart("DOCS", "Where is the creamer kept", None),
        RoutedPart("DOCS", "how many cups do I need for 55 guests?", None),
    )


def test_unreadable_reply_falls_back_to_docs(RouterFake):
    """Covers: AC-3 (wrong), EC-18. 'maybe' is unreadable: DOCS part with the question and fallback True."""
    d = route_fast(RouterFake("maybe"), [], "How many cups for 45 guests?")
    assert d.parts == (RoutedPart("DOCS", "How many cups for 45 guests?", None),)
    assert d.fallback is True
    assert d.kind == "DOCS"
    assert d.unfaithful is False


def test_recipe_question_with_t_reply_becomes_docs(RouterFake):
    """Covers: AC-3 (wrong), EC-18, EC-24. A T for a recipe question: pick_tool is None (recipe tool unavailable), so the part is DOCS; this is not a fallback."""
    q = "How do I make 3 gallons of lemonade?"
    d = route_fast(RouterFake("T"), [], q)
    assert d.parts == (RoutedPart("DOCS", q, None),)
    assert d.kind == "DOCS"
    assert d.fallback is False


def test_follow_up_joins_the_last_user_message(RouterFake):
    """Covers: AC-3 (right), EC-18. A follow-up becomes one part: the previous user message, a space, then the question."""
    fake = RouterFake("T")
    d = route_fast(fake, H_CAMBROS, "4 gallons each.")
    text = "How many cambros do I need for hot water and decaf? 4 gallons each."
    assert d.parts == (RoutedPart("TOOL", text, BEV),)
    assert d.kind == "TOOL"
    assert human_lines(fake) == ["1. " + text]


def test_follow_up_without_number_or_item_makes_no_call(RouterFake):
    """Covers: AC-3 (right), EC-18. 'And the syrups?' after a docs question: one DOCS part, no model call."""
    history = [
        {"role": "user", "content": "Where is the coffee stored?"},
        {"role": "assistant", "content": "Under the coffee machine in the beverage room."},
    ]
    fake = RouterFake()
    d = route_fast(fake, history, "And the syrups?")
    assert d.parts == (RoutedPart("DOCS", "Where is the coffee stored? And the syrups?", None),)
    assert d.kind == "DOCS"
    assert fake.messages == []


def test_follow_up_uses_the_last_user_item(RouterFake):
    """Covers: AC-3 (boundary), EC-18. With several user items, the last one is joined, not the first."""
    history = [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "In the beverage room."},
        {"role": "user", "content": "How many cambros for coffee?"},
        {"role": "assistant", "content": "How many gallons?"},
    ]
    d = route_fast(RouterFake("T"), history, "4 gallons each.")
    assert d.parts == (RoutedPart("TOOL", "How many cambros for coffee? 4 gallons each.", BEV),)


def test_follow_up_question_is_stripped_when_joined(RouterFake):
    """Covers: AC-3 (boundary), EC-18. The question is stripped before it is joined."""
    d = route_fast(RouterFake("T"), H_CAMBROS, "  4 gallons each.  \n")
    assert d.parts[0].text == "How many cambros do I need for hot water and decaf? 4 gallons each."


def test_not_a_follow_up_when_question_has_its_own_starter(RouterFake):
    """Covers: AC-3 (wrong), EC-18. A full question after a history is not joined to it."""
    q = "How many hot cups do I need for 130 guests?"
    d = route_fast(RouterFake("T"), H_CAMBROS, q)
    assert d.parts == (RoutedPart("TOOL", q, BEV),)


def test_summary_only_history_is_not_follow_up_context(RouterFake):
    """Covers: AC-3 (wrong), EC-9, EC-18. A history of only a summary item is not joined: '85 guests.' stays alone."""
    history = [{"role": "summary", "content": "The user asked how many cups to bring."}]
    fake = RouterFake("D")
    d = route_fast(fake, history, "85 guests.")
    assert d.parts == (RoutedPart("DOCS", "85 guests.", None),)


# ---------------------------------------------------------------- EC-19 one call at most

@pytest.mark.parametrize(
    "question,reply,calls",
    [
        (DOCS_Q, None, 0),
        (TOOL_Q, "T", 1),
        (CREAMER_Q, "DT", 1),
        ("How many cups for 5 guests? How many cambros for 6 gallons? Where do the 5 gallon cambros go?", "TTD", 1),
    ],
)
def test_at_most_one_model_call(RouterFake, question, reply, calls):
    """Covers: AC-3 (boundary), EC-19. 0, 1, 2 or 3 parts to label: never more than one model call."""
    fake = RouterFake(*([reply] if reply else []))
    route_fast(fake, [], question)
    assert len(fake.messages) == calls


def test_three_parts_one_call_three_labels(RouterFake):
    """Covers: AC-3 (right), EC-19, EC-18. Three sent parts are labelled by one reply, in order."""
    q = "How many cups for 5 guests? How many cambros for 6 gallons? Where do the 5 gallon cambros go?"
    fake = RouterFake("TTD")
    d = route_fast(fake, [], q)
    assert len(fake.messages) == 1
    assert [p.route for p in d.parts] == ["TOOL", "TOOL", "DOCS"]
    assert [p.tool for p in d.parts] == [BEV, BEV, None]
    assert [p.text for p in d.parts] == [
        "How many cups for 5 guests?",
        "How many cambros for 6 gallons?",
        "Where do the 5 gallon cambros go?",
    ]
    assert d.kind == "BOTH"
    assert human_lines(fake) == [
        "1. How many cups for 5 guests?",
        "2. How many cambros for 6 gallons?",
        "3. Where do the 5 gallon cambros go?",
    ]


def test_second_call_is_never_made_after_a_bad_reply(RouterFake):
    """Covers: AC-3 (wrong), EC-19. An unreadable reply is not retried (a second call would fail the fake)."""
    fake = RouterFake("garbage")
    d = route_fast(fake, [], TOOL_Q)
    assert len(fake.messages) == 1
    assert d.fallback is True


# ---------------------------------------------------------------- EC-20 the call itself

def test_call_messages_shape(RouterFake):
    """Covers: AC-3 (right), EC-20. messages is [SystemMessage(classifier prompt), HumanMessage] with one numbered line per sent part."""
    fake = RouterFake("DT")
    route_fast(fake, [], CREAMER_Q)
    assert len(fake.messages) == 1
    msgs = fake.messages[0]
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage) and isinstance(msgs[1], HumanMessage)
    assert msgs[0].content.strip()
    assert msgs[0].content == classifier_prompt()
    lines = str(msgs[1].content).splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("1. ") and lines[1].startswith("2. ")


def test_call_passes_messages_positionally_and_only_invoke_is_used(RouterFake):
    """Covers: AC-3 (right), EC-20. One positional argument (the messages); the fake has only invoke, so bind or bind_tools would fail."""
    fake = RouterFake("T")
    assert not hasattr(fake, "bind") and not hasattr(fake, "bind_tools") and not hasattr(fake, "with_structured_output")
    route_fast(fake, [], TOOL_Q)
    assert fake.args == [()]
    assert all(isinstance(k, str) for k in fake.kwargs[0])


def test_call_options_do_not_include_tools_or_format(RouterFake):
    """Covers: AC-3 (wrong), EC-20. The keyword arguments are provider options only: no tools, no JSON format, no messages."""
    fake = RouterFake("T")
    route_fast(fake, [], TOOL_Q)
    for forbidden in ("tools", "tool_choice", "format", "messages", "response_format"):
        assert forbidden not in fake.kwargs[0]


def test_router_call_holds_no_history_when_not_a_follow_up(RouterFake):
    """Covers: AC-3 (boundary), EC-20. The model sees only the parts: no history text when the question is standalone."""
    fake = RouterFake("T")
    route_fast(fake, H_CAMBROS, "How many hot cups do I need for 130 guests?")
    sent = "\n".join(str(m.content) for m in fake.messages[0][1:])
    assert "hot water and decaf" not in sent and "each drink" not in sent


def test_nothing_is_printed(RouterFake, capsys):
    """Covers: AC-3 (boundary), section 3.1. route_fast prints nothing."""
    route_fast(RouterFake("T"), H_CAMBROS, "4 gallons each.")
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ---------------------------------------------------------------- EC-21 blank question

@pytest.mark.parametrize("question", ["", " ", "   ", "\n", "\t \n"])
def test_blank_question_raises_before_any_call(RouterFake, question):
    """Covers: AC-3 (wrong), EC-21. A blank question raises ValueError and the model is never called."""
    fake = RouterFake()
    with pytest.raises(ValueError):
        route_fast(fake, H_CAMBROS, question)
    assert fake.messages == []


# ---------------------------------------------------------------- EC-22 reply reading

@pytest.mark.parametrize(
    "reply",
    ["TD", "T D", "t,d", "TOOL DOCS", "Tool, docs", "TD because it asks", "1. T\n2. D", "T-D", "t\nd", "Tool D"],
)
def test_readable_replies_read_as_tool_then_docs(RouterFake, reply):
    """Covers: AC-3 (right), EC-22. Letters, words, any case and any separators read as T then D; extra words after enough labels are ignored."""
    d = route_fast(RouterFake(reply), [], TWO_TOOL_Q)
    assert d.fallback is False
    assert [p.route for p in d.parts] == ["TOOL", "DOCS"]
    assert [p.tool for p in d.parts] == [BEV, None]
    assert d.kind == "BOTH"


@pytest.mark.parametrize("reply", ["", "yes", "The answer is T", "T", "TX", "yes T", "maybe D", "   ", "...", "12"])
def test_unreadable_replies_for_two_parts_fall_back(RouterFake, reply):
    """Covers: AC-3 (wrong), EC-22. Empty, off-format, too short or mixed-letter replies: every sent part DOCS and fallback True."""
    d = route_fast(RouterFake(reply), [], TWO_TOOL_Q)
    assert d.fallback is True
    assert [p.route for p in d.parts] == ["DOCS", "DOCS"]
    assert [p.tool for p in d.parts] == [None, None]
    assert [p.text for p in d.parts] == ["How many cups for 55 guests?", "Do I bring sugar for hot water?"]
    assert d.kind == "DOCS"


@pytest.mark.parametrize("reply", ["T because the question asks for an amount", "Tool. It is a count.", "T, how many cups"])
def test_extra_tokens_after_enough_labels_are_ignored(RouterFake, reply):
    """Covers: AC-3 (boundary), EC-22. For one sent part, tokens after the first label are not read (so they cannot make the reply unreadable)."""
    d = route_fast(RouterFake(reply), [], TOOL_Q)
    assert d.fallback is False
    assert d.parts == (RoutedPart("TOOL", TOOL_Q, BEV),)


@pytest.mark.parametrize("reply,route", [("D", "DOCS"), ("d", "DOCS"), ("DOCS", "DOCS"), ("docs.", "DOCS"), ("Documents", "DOCS"), ("T", "TOOL"), ("TOOL", "TOOL")])
def test_single_part_labels(RouterFake, reply, route):
    """Covers: AC-3 (right), EC-22. A token starting with 'doc' is D; a token starting with 'tool' or the letter T is T."""
    d = route_fast(RouterFake(reply), [], TOOL_Q)
    assert d.parts[0].route == route
    assert d.fallback is False
    assert d.parts[0].tool == (BEV if route == "TOOL" else None)


def test_non_letter_prefix_does_not_hide_the_label(RouterFake):
    """Covers: AC-3 (boundary), EC-22. Digits and punctuation split tokens: '1) T' reads as T."""
    d = route_fast(RouterFake("1) T"), [], TOOL_Q)
    assert d.parts[0].route == "TOOL" and d.fallback is False


def test_unreadable_reply_for_three_parts(RouterFake):
    """Covers: AC-3 (wrong), EC-22. Two letters for three sent parts: fallback, all three DOCS."""
    q = "How many cups for 5 guests? How many cambros for 6 gallons? Where do the 5 gallon cambros go?"
    d = route_fast(RouterFake("TT"), [], q)
    assert d.fallback is True
    assert [p.route for p in d.parts] == ["DOCS", "DOCS", "DOCS"]


# ---------------------------------------------------------------- EC-23 history untouched

@pytest.mark.parametrize("question", ["4 gallons each.", "How many hot cups do I need for 130 guests?", "And the syrups?"])
def test_history_is_never_changed(RouterFake, question):
    """Covers: AC-3 (boundary), EC-23. The history list and its items are the same after the call (follow-up or not)."""
    history = copy.deepcopy(H_CAMBROS)
    snapshot = copy.deepcopy(history)
    route_fast(RouterFake("T"), history, question)
    assert history == snapshot


# ---------------------------------------------------------------- EC-24 the tool guard

def test_tool_part_with_no_item_or_recipe_word_becomes_docs(RouterFake):
    """Covers: AC-3 (wrong), EC-24. 'When does setup start for the 6 pm event?' has a number only: the model says T but pick_tool is None, so DOCS."""
    q = "When does setup start for the 6 pm event?"
    d = route_fast(RouterFake("T"), [], q)
    assert d.parts == (RoutedPart("DOCS", q, None),)
    assert d.fallback is False
    assert d.kind == "DOCS"


def test_mixed_labels_guard_only_the_tool_part_without_a_tool(RouterFake):
    """Covers: AC-3 (boundary), EC-24. Two sent parts, both T: the one with an item word stays TOOL, the one without becomes DOCS."""
    q = "How many cups for 55 guests? When does setup start for the 6 pm event?"
    d = route_fast(RouterFake("TT"), [], q)
    assert [p.route for p in d.parts] == ["TOOL", "DOCS"]
    assert [p.tool for p in d.parts] == [BEV, None]
    assert d.kind == "BOTH"


def test_docs_part_never_has_a_tool(RouterFake):
    """Covers: AC-3 (wrong), section 4.5 step 5. A D label gives a DOCS part with tool None, even when the text has item words."""
    d = route_fast(RouterFake("D"), [], "Where do the 5 gallon cambros go?")
    assert d.parts[0].route == "DOCS" and d.parts[0].tool is None


# ---------------------------------------------------------------- EC-25 RoutedPart default

def test_routed_part_two_arguments_still_work():
    """Covers: AC-3 (right), EC-25. RoutedPart with two arguments has tool None."""
    assert RoutedPart("DOCS", "x").tool is None
    assert RoutedPart("TOOL", "x").tool is None
    assert RoutedPart("TOOL", "x") == RoutedPart("TOOL", "x", None)


def test_routed_part_tool_field_is_kept_and_frozen():
    """Covers: AC-3 (right), EC-25. A third argument is stored in `tool`; the dataclass stays frozen and compares by value."""
    p = RoutedPart("TOOL", "x", BEV)
    assert p.tool == BEV and p.route == "TOOL" and p.text == "x"
    assert p != RoutedPart("TOOL", "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.tool = None


def test_route_decision_old_construction_still_works():
    """Covers: AC-3 (right), EC-25. RouteDecision(parts, kind, fallback) built as in spec 006 tests still works."""
    d = RouteDecision((RoutedPart("DOCS", "x"),), "DOCS", False)
    assert d.kind == "DOCS" and d.fallback is False and d.unfaithful is False

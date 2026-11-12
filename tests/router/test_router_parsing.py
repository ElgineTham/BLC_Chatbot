"""AC-1: route_question parsing (EC-1 to EC-3). Unit tests with a fake model; no Ollama, no network."""

from __future__ import annotations

import dataclasses

import pytest
from langchain_core.messages import AIMessage

from blc.router import ROUTE_KINDS, ROUTES, RouteDecision, RoutedPart, route_question

Q = "How many cups do I need for 45 guests?"
HISTORY = [
    {"role": "user", "content": "earlier question zebra"},
    {"role": "assistant", "content": "earlier answer giraffe"},
]


class FakeRouterModel:
    """Returns one scripted reply; records every invoke and every bind_tools call."""

    def __init__(self, reply):
        self.reply = reply
        self.invocations = []
        self.bind_calls = []

    def invoke(self, messages, *args, **kwargs):
        self.invocations.append(list(messages))
        return AIMessage(content=self.reply)

    def bind_tools(self, *args, **kwargs):
        self.bind_calls.append(args)
        raise AssertionError("route_question must not bind tools")


def route(reply, question=Q, history=None):
    return route_question(FakeRouterModel(reply), [] if history is None else history, question)


def pairs(decision):
    return [(p.route, p.text) for p in decision.parts]


# ---------------------------------------------------------------- contract

def test_constants():
    """Covers: AC-1 (right). ROUTES and ROUTE_KINDS as in the contract."""
    assert ROUTES == ("TOOL", "DOCS")
    assert ROUTE_KINDS == ("TOOL", "DOCS", "BOTH")


def test_dataclasses_are_frozen():
    """Covers: AC-1 (wrong). RoutedPart and RouteDecision are frozen dataclasses."""
    part = RoutedPart("TOOL", "x")
    decision = RouteDecision((part,), "TOOL", False)
    assert (part.route, part.text) == ("TOOL", "x")
    assert (decision.parts, decision.kind, decision.fallback) == ((part,), "TOOL", False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        part.route = "DOCS"
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.kind = "DOCS"


def test_returns_route_decision_with_tuple_of_parts():
    """Covers: AC-1 (right). The result is a RouteDecision whose parts is a tuple of RoutedPart."""
    d = route("TOOL: How many cups for 45 guests?")
    assert isinstance(d, RouteDecision)
    assert isinstance(d.parts, tuple)
    assert all(isinstance(p, RoutedPart) for p in d.parts)


# ---------------------------------------------------------------- EC-1: the section 4.1 table

def test_table_single_tool():
    """Covers: AC-1 (right), EC-1. A single TOOL line gives one TOOL part."""
    d = route("TOOL: How many cambros for 6 gallons of peach tea?")
    assert pairs(d) == [("TOOL", "How many cambros for 6 gallons of peach tea?")]
    assert d.kind == "TOOL"
    assert d.fallback is False


def test_table_docs_then_tool():
    """Covers: AC-1 (right), EC-1, EC-2. DOCS then TOOL lines give two parts in order and kind BOTH."""
    d = route("DOCS: Where are lemons kept?\nTOOL: How many cold cups for 45 guests?")
    assert pairs(d) == [("DOCS", "Where are lemons kept?"), ("TOOL", "How many cold cups for 45 guests?")]
    assert d.kind == "BOTH"
    assert d.fallback is False


def test_table_bold_mixed_case_label():
    """Covers: AC-1 (right), EC-1. '**Tool**:' is a TOOL label."""
    d = route("**Tool**: How many gallons of iced tea for 90 guests?")
    assert pairs(d) == [("TOOL", "How many gallons of iced tea for 90 guests?")]


def test_table_numbered_lowercase_label():
    """Covers: AC-1 (right), EC-1. '1. docs:' is a DOCS label."""
    d = route("1. docs: What does fresh-brewed mean?")
    assert pairs(d) == [("DOCS", "What does fresh-brewed mean?")]
    assert d.kind == "DOCS"


def test_table_unlabelled_sentence_falls_back():
    """Covers: AC-1 (wrong), EC-1. No label: one DOCS part with the whole question and fallback=True."""
    d = route("I think this is a tool question.")
    assert pairs(d) == [("DOCS", Q)]
    assert d.kind == "DOCS"
    assert d.fallback is True


@pytest.mark.parametrize("reply", ["", "   ", "\n\n"])
def test_table_empty_reply_falls_back(reply):
    """Covers: AC-1 (wrong, boundary), EC-1. An empty or blank reply gives the fallback and does not raise."""
    d = route(reply)
    assert pairs(d) == [("DOCS", Q)]
    assert d.fallback is True


# ---------------------------------------------------------------- label decorations

@pytest.mark.parametrize(
    "line, route_name",
    [
        ("- TOOL: text here cups", "TOOL"),
        ("* TOOL: text here cups", "TOOL"),
        ("# DOCS: text here cups", "DOCS"),
        ("2. TOOL: text here cups", "TOOL"),
        ("12. docs: text here cups", "DOCS"),
        ("**DOCS**: text here cups", "DOCS"),
        ("- **Tool**: text here cups", "TOOL"),
        ("tool: text here cups", "TOOL"),
        ("Docs: text here cups", "DOCS"),
        ("tOoL: text here cups", "TOOL"),
        ("   TOOL:   text here cups   ", "TOOL"),
    ],
)
def test_label_decorations_and_case(line, route_name):
    """Covers: AC-1 (right), EC-1. Leading -, *, #, list numbers, ** around the label and any case are accepted; text is stripped."""
    d = route(line)
    assert pairs(d) == [(route_name, "text here cups")]
    assert d.fallback is False


def test_text_keeps_later_colons():
    """Covers: AC-1 (boundary), EC-1. Only the label's colon is consumed; the rest of the line is the text."""
    d = route("TOOL: Cambros: how many for 4 gallons?")
    assert pairs(d) == [("TOOL", "Cambros: how many for 4 gallons?")]


# ---------------------------------------------------------------- unlabelled lines and empty text

def test_unlabelled_lines_are_ignored_between_labelled_ones():
    """Covers: AC-1 (right), EC-1. Lines without a label are ignored and blank lines skipped; fallback stays False."""
    reply = "Here is my split:\n\nDOCS: Where is the coffee?\nsome remark\n\nTOOL: How many cups for 45 guests?\nThanks!"
    d = route(reply)
    assert pairs(d) == [("DOCS", "Where is the coffee?"), ("TOOL", "How many cups for 45 guests?")]
    assert d.fallback is False


def test_label_without_colon_is_not_a_label():
    """Covers: AC-1 (wrong), EC-1. 'TOOL' not followed by a colon gives no part: fallback."""
    d = route("TOOL how many cups for 45 guests")
    assert pairs(d) == [("DOCS", Q)]
    assert d.fallback is True


def test_label_not_at_line_start_is_not_a_label():
    """Covers: AC-1 (wrong), EC-1. The label must start the line (after the allowed decorations)."""
    d = route("This is a TOOL: question")
    assert d.fallback is True
    assert pairs(d) == [("DOCS", Q)]


@pytest.mark.parametrize("reply, route_name", [("TOOL:", "TOOL"), ("DOCS:   ", "DOCS"), ("- docs:", "DOCS")])
def test_labelled_line_with_empty_text_uses_whole_question(reply, route_name):
    """Covers: AC-1 (boundary), EC-1. A label with no text takes the whole question as its text; not a fallback."""
    d = route(reply)
    assert pairs(d) == [(route_name, Q)]
    assert d.fallback is False


def test_empty_text_part_among_others():
    """Covers: AC-1 (boundary), EC-1. Only the empty-text part gets the whole question."""
    d = route("DOCS: Where is the coffee?\nTOOL:")
    assert pairs(d) == [("DOCS", "Where is the coffee?"), ("TOOL", Q)]


# ---------------------------------------------------------------- EC-2: kind and order

def test_kind_all_tool():
    """Covers: AC-1 (right), EC-2. All TOOL parts give kind TOOL."""
    d = route("TOOL: a cups?\nTOOL: b napkins?")
    assert d.kind == "TOOL"
    assert len(d.parts) == 2


def test_kind_all_docs():
    """Covers: AC-1 (right), EC-2. All DOCS parts give kind DOCS."""
    d = route("DOCS: a?\nDOCS: b?\nDOCS: c?")
    assert d.kind == "DOCS"
    assert len(d.parts) == 3


def test_kind_both_tool_first():
    """Covers: AC-1 (right), EC-2. TOOL then DOCS gives kind BOTH."""
    assert route("TOOL: a cups?\nDOCS: b?").kind == "BOTH"


def test_order_is_kept():
    """Covers: AC-1 (right), EC-2. Parts keep the reply's order, repeated routes included."""
    d = route("TOOL: one cups?\nDOCS: two?\nTOOL: three napkins?")
    assert pairs(d) == [("TOOL", "one cups?"), ("DOCS", "two?"), ("TOOL", "three napkins?")]
    assert d.kind == "BOTH"


def test_kind_is_always_a_known_kind_and_parts_never_empty():
    """Covers: AC-1 (boundary), EC-2. Even for unreadable replies kind is in ROUTE_KINDS and there is at least one part."""
    for reply in ("", "nonsense", "TOOL: How many cups?", "DOCS: y"):
        d = route(reply)
        assert d.kind in ROUTE_KINDS
        assert len(d.parts) >= 1
        assert all(p.route in ROUTES for p in d.parts)


# ---------------------------------------------------------------- EC-3: blank question, messages

@pytest.mark.parametrize("question", ["", " ", "   \n\t "])
def test_blank_question_raises_without_model_call(question):
    """Covers: AC-1 (wrong, boundary), EC-3. A blank question raises ValueError and the model is never called."""
    model = FakeRouterModel("TOOL: How many cups?")
    with pytest.raises(ValueError):
        route_question(model, [], question)
    assert model.invocations == []
    assert model.bind_calls == []


def test_blank_question_with_history_still_raises():
    """Covers: AC-1 (wrong), EC-3. History does not make a blank question valid."""
    model = FakeRouterModel("TOOL: How many cups?")
    with pytest.raises(ValueError):
        route_question(model, HISTORY, "  ")
    assert model.invocations == []


def test_one_call_with_question_and_history_and_no_tool_bound():
    """Covers: AC-1 (right), EC-3. Exactly one llm.invoke; messages contain the question and history content; bind_tools is never called."""
    model = FakeRouterModel("DOCS: where?")
    route_question(model, HISTORY, "Where is the stirrer kept please")
    assert len(model.invocations) == 1
    body = "\n".join(str(m.content) for m in model.invocations[0])
    assert "Where is the stirrer kept please" in body
    assert "earlier question zebra" in body
    assert "earlier answer giraffe" in body
    assert model.bind_calls == []


def test_one_call_with_empty_history():
    """Covers: AC-1 (boundary), EC-3. Empty history works and the question is in the messages."""
    model = FakeRouterModel("DOCS: where?")
    route_question(model, [], Q)
    assert len(model.invocations) == 1
    assert Q in "\n".join(str(m.content) for m in model.invocations[0])


def test_fallback_uses_the_question_as_given():
    """Covers: AC-1 (right), EC-1. The fallback part's text is the question passed in."""
    d = route_question(FakeRouterModel("no idea"), [], "Where are the lemons?")
    assert pairs(d) == [("DOCS", "Where are the lemons?")]


def test_route_question_prints_nothing_and_leaves_history_unchanged(capsys):
    """Covers: AC-1 (boundary), spec 3.1 'Prints nothing'. Nothing is printed and the history is not modified."""
    history = [dict(m) for m in HISTORY]
    route_question(FakeRouterModel("TOOL: How many cups?"), history, Q)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert history == HISTORY

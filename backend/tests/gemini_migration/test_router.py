"""Spec 037 section 6.3 (ROUTER-1): route_fast calls invoke without Ollama-specific keywords."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from blc.router import RoutedPart, route_fast


class RecordingFake:
    """Scripted router model with only `invoke`; records args and kwargs of every call."""

    def __init__(self, *replies):
        self.script = list(replies)
        self.args = []
        self.kwargs = []

    def invoke(self, messages, *args, **kwargs):
        self.args.append(args)
        self.kwargs.append(kwargs)
        if not self.script:
            raise AssertionError("invoke called more times than scripted")
        return AIMessage(content=self.script.pop(0))


@pytest.mark.parametrize(
    "question",
    [
        "How many hot cups for 130 guests?",
        "How many cambros do I need for 7 gallons of lemonade?",
    ],
)
def test_invoke_has_no_options_or_keep_alive(question):
    """Covers: AC-9 (right), ROUTER-1. The model call carries no `options` and no `keep_alive` keyword."""
    fake = RecordingFake("T")
    decision = route_fast(fake, [], question)
    assert len(fake.kwargs) == 1, "the question needs the model, so exactly one invoke is expected"
    assert "options" not in fake.kwargs[0]
    assert "keep_alive" not in fake.kwargs[0]
    assert decision.kind == "TOOL"


def test_invoke_has_no_positional_options_dict():
    """Covers: AC-9 (wrong). No extra positional argument smuggles Ollama options in."""
    fake = RecordingFake("T")
    route_fast(fake, [], "How many hot cups for 130 guests?")
    assert all(not any(isinstance(a, dict) for a in args) for args in fake.args)


def test_docs_question_still_needs_no_call():
    """Covers: AC-9 (boundary). Unchanged behaviour: a plain DOCS question makes no model call."""
    fake = RecordingFake()
    d = route_fast(fake, [], "Where is the coffee?")
    assert d.parts == (RoutedPart("DOCS", "Where is the coffee?", None),)
    assert fake.kwargs == []

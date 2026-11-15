"""Spec 023, section 6.3 (DOCS path): DOCS-1 to DOCS-3; AC-7, AC-8, AC-9 (word checks).

Unit: scripted fake models, fake store.
"""
from langchain_core.messages import SystemMessage

from blc.flow import FLOW_ANSWER_PROMPT, NO_DOCS_REPLY

SEARCH = "search_documents"
Q = "Where is the coffee?"


def test_docs_1_streamed_answer_with_chunks(run, doc):
    """Covers: AC-7 (right), DOCS-1. Reply 'AB'; pieces 'A','B'; answered_by_model True; last message has the
    question, chunks and sources."""
    docs = {"coffee": [doc("Coffee is in the pantry.", "data/a.md"), doc("Urns by the sink.", "data/b.md")]}
    r = run(Q, [(SEARCH, {"query": "coffee"})], docs=docs, pieces=("A", "B"))
    assert r.outcome.reply == "AB"
    assert r.tokens == ["A", "B"]
    assert r.outcome.answered_by_model is True
    last = r.llm.stream_calls[0][-1].content
    for token in (Q, "Coffee is in the pantry.", "data/a.md", "Urns by the sink.", "data/b.md"):
        assert token in last, token


def test_docs_1_one_stream_one_planner_call(run, doc):
    """Covers: AC-8 (boundary), DOCS-1. One planner call and one stream call."""
    r = run(Q, [(SEARCH, {"query": "coffee"})], docs={"coffee": [doc("X.", "data/a.md")]})
    assert len(r.llm.invoke_calls) == 1
    assert len(r.llm.stream_calls) == 1


def test_docs_1_no_separator_prefix_on_docs_only(run, doc):
    """Covers: AC-7 (wrong), DOCS-1. A docs-only reply has no tool part, so no leading blank line or extra piece."""
    r = run(Q, [(SEARCH, {"query": "coffee"})], docs={"coffee": [doc("X.", "data/a.md")]},
            pieces=("  A", "B\n"))
    assert r.tokens == ["  A", "B\n"]
    assert r.outcome.reply == "AB"


def test_docs_2_no_chunks_gives_no_docs_reply(run):
    """Covers: AC-7 (right), DOCS-2. All searches return []: NO_DOCS_REPLY, once, no model call."""
    r = run(Q, [(SEARCH, {"query": "a"}), (SEARCH, {"query": "b"})], docs={})
    assert r.outcome.reply == NO_DOCS_REPLY
    assert r.tokens == [NO_DOCS_REPLY]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_docs_2_one_search_with_chunks_among_empty(run, doc):
    """Covers: AC-7 (boundary), DOCS-2. One non-empty search is enough to call the model."""
    r = run(Q, [(SEARCH, {"query": "a"}), (SEARCH, {"query": "b"})],
            docs={"b": [doc("B.", "data/b.md")]}, pieces=("Ok.",))
    assert r.outcome.reply == "Ok."
    assert len(r.llm.stream_calls) == 1


def test_docs_3_prompt_words_and_first_message(run, doc):
    """Covers: AC-7 (right), AC-9, DOCS-3. FLOW_ANSWER_PROMPT is the first message of the answer call and contains
    'simple', 'straightforward', 'grounded'."""
    r = run(Q, [(SEARCH, {"query": "coffee"})], docs={"coffee": [doc("X.", "data/a.md")]})
    first = r.llm.stream_calls[0][0]
    assert isinstance(first, SystemMessage)
    assert first.content == FLOW_ANSWER_PROMPT
    low = FLOW_ANSWER_PROMPT.lower()
    for word in ("simple", "straightforward", "grounded"):
        assert word in low, word

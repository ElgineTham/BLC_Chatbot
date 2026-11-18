"""Spec 023, section 6.2 (BOTH path): BOTH-1 to BOTH-10; AC-3, AC-4, AC-5, AC-6, AC-8.

Unit: scripted fake models, fake store, fake runners.
"""
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from blc.flow import FLOW_ANSWER_PROMPT, NO_DOCS_REPLY, TOOL_FAILED_REPLY

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
H = "Hot cups: 60 for 40 guests (40 guests plus 20 extras)."
Q = "Where is the coffee, and how many cambros for 6 gallons of iced tea?"
BEV_ARGS = {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}
SEARCH_ARGS = {"query": "where is the coffee"}


@pytest.fixture
def docs(doc):
    return {"where is the coffee": [doc("The coffee is in the pantry.", "data/supplies/coffee.md"),
                                    doc("Hot cups sit by the urns.", "data/supplies/cups.md")]}


def _both(run, make_runner, docs, **kw):
    runners = kw.pop("runners", None) or {BEV: make_runner("ok", H), REC: make_runner("ok", "B")}
    pieces = kw.pop("pieces", ("In the ", "pantry."))
    return run(Q, [(BEV, BEV_ARGS), (SEARCH, SEARCH_ARGS)], runners=runners, docs=docs,
               pieces=pieces, **kw)


def test_both_1_reply_and_tokens(run, make_runner, docs):
    """Covers: AC-4 (right), BOTH-1. Reply is H + blank line + answer; first on_token piece is H + blank line,
    then each streamed piece; answered_by_model True."""
    r = _both(run, make_runner, docs)
    assert r.outcome.reply == H + "\n\nIn the pantry."
    assert r.tokens == [H + "\n\n", "In the ", "pantry."]
    assert r.outcome.answered_by_model is True
    assert len(r.llm.stream_calls) == 1


def test_both_1_history_has_full_reply(run, make_runner, docs):
    """Covers: AC-4 (right), BOTH-9. History ends with the user question and the full reply."""
    r = _both(run, make_runner, docs)
    assert r.outcome.history[-2:] == [{"role": "user", "content": Q},
                                      {"role": "assistant", "content": H + "\n\nIn the pantry."}]


def test_both_2_tool_part_sent_before_model_is_called(run, make_runner, docs):
    """Covers: AC-4 (right), BOTH-2. The first recorded event is the tool-part token, before stream."""
    r = _both(run, make_runner, docs)
    assert r.events[0] == ("token", H + "\n\n")
    assert r.events.index(("stream", None)) > 0
    assert [e for e in r.events if e[0] == "token"][0] == r.events[0]


def test_both_3_model_messages_have_no_tool_text(run, make_runner, docs, text_of):
    """Covers: AC-5 (wrong), BOTH-3. No message holds tool text; the last has question, query, chunks, sources."""
    r = _both(run, make_runner, docs)
    msgs = r.llm.stream_calls[0]
    assert "Hot cups: 60" not in text_of(msgs)
    assert "40 guests plus 20 extras" not in text_of(msgs)
    last = msgs[-1].content
    for token in (Q, "where is the coffee", "The coffee is in the pantry.", "data/supplies/coffee.md",
                  "Hot cups sit by the urns.", "data/supplies/cups.md"):
        assert token in last, token


def test_both_3_message_shape(run, make_runner, docs):
    """Covers: AC-5 (right), BOTH-3. First message is the system prompt, last a HumanMessage, no tools bound
    for the answer call."""
    r = _both(run, make_runner, docs)
    msgs = r.llm.stream_calls[0]
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == FLOW_ANSWER_PROMPT
    assert isinstance(msgs[-1], HumanMessage)
    assert len(r.llm.bind_calls) == 1  # the planner only


def test_both_4_invalid_tool_sentence_first_and_hidden_from_model(run, make_runner, docs, text_of):
    """Covers: AC-3 (right), AC-5 (wrong), BOTH-4. Reply starts with the friendly sentence; neither the raw text
    nor the sentence reaches the model."""
    raw = "invalid request: RAWTEXT Expected arguments: {}"
    runners = {BEV: make_runner("invalid", raw), REC: make_runner("ok", "x")}
    r = _both(run, make_runner, docs, runners=runners)
    assert r.outcome.reply.startswith(TOOL_FAILED_REPLY + "\n\n")
    assert r.outcome.reply.endswith("In the pantry.")
    assert r.tokens[0] == TOOL_FAILED_REPLY + "\n\n"
    assert all("RAWTEXT" not in t for t in r.tokens)
    joined = text_of(r.llm.stream_calls[0])
    assert "RAWTEXT" not in joined
    assert TOOL_FAILED_REPLY not in joined
    assert "I couldn't work that out" not in joined


def test_both_5_every_search_query_reaches_the_model(run, make_runner, doc):
    """Covers: AC-5 (right), BOTH-5. Two searches and one tool: the last message contains both queries."""
    docs = {"where is the coffee": [doc("Coffee doc.", "data/a.md")],
            "where are the cups": [doc("Cups doc.", "data/b.md")]}
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(Q, [(SEARCH, SEARCH_ARGS), (SEARCH, {"query": "where are the cups"}), (BEV, BEV_ARGS)],
            runners=runners, docs=docs, pieces=("Ok.",))
    last = r.llm.stream_calls[0][-1].content
    assert "where is the coffee" in last and "where are the cups" in last
    assert "Hot cups: 60" not in last
    assert r.outcome.reply == H + "\n\nOk."


def test_both_6_no_chunks_gives_no_docs_reply_after_tools(run, make_runner):
    """Covers: AC-6 (right), BOTH-6. Search returns []: reply is H + blank line + NO_DOCS_REPLY, one on_token call,
    no model call, answered_by_model False."""
    r = _both(run, make_runner, {})
    expected = H + "\n\n" + NO_DOCS_REPLY
    assert r.outcome.reply == expected
    assert r.tokens == [expected]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_both_6_failed_tool_with_no_chunks(run, make_runner):
    """Covers: AC-6 (boundary), AC-3. A failed tool shows the sentence, then NO_DOCS_REPLY."""
    runners = {BEV: make_runner("error", "error: boom"), REC: make_runner("ok", "x")}
    r = _both(run, make_runner, {}, runners=runners)
    assert r.outcome.reply == TOOL_FAILED_REPLY + "\n\n" + NO_DOCS_REPLY
    assert "boom" not in r.outcome.reply


def test_both_7_streamed_whitespace_kept_in_tokens_stripped_in_reply(run, make_runner, docs):
    """Covers: AC-4 (boundary), BOTH-7. Model streams '  In the pantry.\\n': reply ends with 'In the pantry.' after the
    blank line; on_token got the pieces as streamed."""
    r = _both(run, make_runner, docs, pieces=("  In the ", "pantry.\n"))
    assert r.outcome.reply == H + "\n\nIn the pantry."
    assert r.tokens[0] == H + "\n\n"
    assert r.tokens[1:] == ["  In the ", "pantry.\n"]
    assert r.outcome.history[-1]["content"] == r.outcome.reply


def test_both_8_need_info_text_then_model_answer(run, make_runner, docs):
    """Covers: AC-4 (right), BOTH-8. need_info plus a search with chunks: reply starts with the question text,
    blank line; model called once."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = _both(run, make_runner, docs, runners=runners)
    assert r.outcome.reply.startswith("Which drink?\n\n")
    assert r.outcome.reply.endswith("In the pantry.")
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.answered_by_model is True


def test_both_9_history_reaches_the_model_verbatim(run, make_runner, docs, text_of):
    """Covers: AC-4 (right), AC-5 (right), BOTH-9. Non-empty history is in the model messages; outcome.history
    ends with the user question and the full reply."""
    history = [{"role": "user", "content": "Earlier question about urns?"},
               {"role": "assistant", "content": "Earlier answer about urns."}]
    r = _both(run, make_runner, docs, history=history)
    joined = text_of(r.llm.stream_calls[0])
    assert "Earlier question about urns?" in joined
    assert "Earlier answer about urns." in joined
    assert "Hot cups: 60" not in joined
    assert r.outcome.history[:2] == history
    assert r.outcome.history[-2:] == [{"role": "user", "content": Q},
                                      {"role": "assistant", "content": H + "\n\nIn the pantry."}]


def test_both_10_model_called_once_without_retry(run, make_runner, docs):
    """Covers: AC-8 (boundary), BOTH-10. A clean BOTH turn: one planner call, one stream call."""
    r = _both(run, make_runner, docs)
    assert len(r.llm.invoke_calls) == 1
    assert len(r.llm.stream_calls) == 1


def test_both_10_retry_keeps_one_stream_call(run, make_runner, docs):
    """Covers: AC-8 (boundary), BOTH-10. A spec 021 retry (invented 6 for 60 gallons) makes at most two planner
    calls and still only one stream call; tool text stays out of the model."""
    q = "Where is the coffee, and how many cambros for 60 gallons of coffee?"
    bad = {"item": "cambros", "drinks": ["coffee"], "gallons": [6]}
    good = {"item": "cambros", "drinks": ["coffee"], "gallons": [60]}
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(q, [[(SEARCH, SEARCH_ARGS), (BEV, bad)], [(SEARCH, SEARCH_ARGS), (BEV, good)]],
            runners=runners, docs=docs, pieces=("In the ", "pantry."))
    assert len(r.llm.invoke_calls) <= 2
    assert len(r.llm.stream_calls) == 1
    assert "Hot cups: 60" not in str(r.llm.stream_calls[0][-1].content)
    assert r.outcome.reply.startswith(H + "\n\n")

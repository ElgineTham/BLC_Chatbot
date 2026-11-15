"""Spec 019, AC-2 (reply rules) and AC-3 (streaming): EC-5, EC-6, EC-7, EC-9, NFR-5.

Unit: scripted fake models, fake store, fake runners.
"""
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from blc.flow import FLOW_ANSWER_PROMPT, NO_DOCS_REPLY

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
BEV_ARGS = {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}
REC_ARGS = {"recipe": "lemonade", "gallons": 4}


# ---------------------------------------------------------------- EC-5 pass-through

def test_single_need_info_is_passed_through_without_answer_call(run, make_runner):
    """Covers: AC-2 (right), EC-5. One need_info tool and no searches: the reply is its text,
    on_token is called once with it, the answer model is not called."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = run("How many cambros?", [(BEV, {"item": "cambros"})], runners=runners)
    assert r.outcome.reply == "Which drink?"
    assert r.tokens == ["Which drink?"]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_several_need_info_texts_are_joined_in_plan_order(run, make_runner):
    """Covers: AC-2 (right), EC-5. Two need_info results: texts joined with a newline, in plan order,
    sent to on_token once."""
    runners = {BEV: make_runner("need_info", "Which drink?"),
               REC: make_runner("need_info", "Which recipe?")}
    r = run("q", [(REC, {}), (BEV, {})], runners=runners)
    assert r.outcome.reply == "Which recipe?\nWhich drink?"
    assert r.tokens == ["Which recipe?\nWhich drink?"]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert [t.status for t in r.outcome.tools] == ["need_info", "need_info"]


def test_pass_through_does_not_touch_the_store(run, make_runner):
    """Covers: AC-2 (right), EC-5. Tools only: no search happens."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, {})], runners=runners)
    assert r.store.calls == []


def test_pass_through_history_gets_the_question_as_reply(run, make_runner):
    """Covers: AC-2 (right), EC-5. The assistant history item is the passed-through question."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = run("How many cambros?", [(BEV, {})], runners=runners)
    assert r.outcome.history == [{"role": "user", "content": "How many cambros?"},
                                 {"role": "assistant", "content": "Which drink?"}]


def test_pass_through_works_without_on_token(run, make_runner):
    """Covers: AC-2 (boundary), EC-5, EC-9. on_token=None with a pass-through reply."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, {})], runners=runners, on_token=None)
    assert r.outcome.reply == "Which drink?"


# ---------------------------------------------------------------- EC-6 not pass-through

def test_need_info_with_a_search_still_calls_the_answer_model(run, make_runner, doc):
    """Covers: AC-2 (wrong), EC-6. need_info plus a search: the answer model is called."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, {}), (SEARCH, {"query": "x"})], runners=runners,
            docs={"x": [doc("Doc.", "data/a.md")]}, pieces=("Fine.",))
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.answered_by_model is True
    assert "Which drink?" in r.llm.stream_calls[0][-1].content


def test_need_info_with_an_empty_search_still_calls_the_answer_model(run, make_runner):
    """Covers: AC-2 (wrong), EC-6, EC-7. A search call exists (even with no chunks), so the first
    rule does not apply; a tool call exists, so NO_DOCS_REPLY does not apply."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, {}), (SEARCH, {"query": "x"})], runners=runners, pieces=("Fine.",))
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.answered_by_model is True


def test_need_info_with_an_ok_tool_calls_the_answer_model(run, make_runner):
    """Covers: AC-2 (wrong), EC-6. need_info plus an ok result: the answer model is called."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("ok", "Use 14 oz.")}
    r = run("q", [(BEV, {}), (REC, REC_ARGS)], runners=runners, pieces=("Fine.",))
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.answered_by_model is True
    last = r.llm.stream_calls[0][-1].content
    assert "Which drink?" in last and "Use 14 oz." in last


def test_need_info_with_an_invalid_tool_calls_the_answer_model(run, make_runner):
    """Covers: AC-2 (boundary), EC-6. Only the status need_info is passed through; invalid is not."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("invalid", "no recipe")}
    r = run("q", [(BEV, {}), (REC, REC_ARGS)], runners=runners, pieces=("Fine.",))
    assert len(r.llm.stream_calls) == 1


def test_single_ok_tool_is_not_passed_through(run, make_runner):
    """Covers: AC-2 (wrong), EC-6. An ok result is answered by the model."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=("Bring 2 cambros.",))
    assert r.outcome.reply == "Bring 2 cambros."
    assert r.outcome.answered_by_model is True


# ---------------------------------------------------------------- EC-7 no documents

def test_no_chunks_and_no_tools_gives_no_docs_reply(run):
    """Covers: AC-2 (right), EC-7. Every search returns [] and there are no tool calls:
    NO_DOCS_REPLY, sent once, no answer call, answered_by_model False."""
    r = run("Where is the unicorn?", [(SEARCH, {"query": "unicorn"})], docs={})
    assert r.outcome.reply == NO_DOCS_REPLY
    assert r.tokens == [NO_DOCS_REPLY]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert r.outcome.documents == ()
    assert r.outcome.history[-1] == {"role": "assistant", "content": NO_DOCS_REPLY}


def test_no_docs_reply_with_several_empty_searches(run):
    """Covers: AC-2 (boundary), EC-7. Two searches, both empty."""
    r = run("q", [(SEARCH, {"query": "a"}), (SEARCH, {"query": "b"})], docs={})
    assert r.outcome.reply == NO_DOCS_REPLY
    assert r.llm.stream_calls == []
    assert len(r.outcome.searches) == 2


def test_one_search_with_chunks_among_empty_ones_calls_the_answer_model(run, doc):
    """Covers: AC-2 (wrong), EC-7. Only when every search is empty is the model skipped."""
    r = run("q", [(SEARCH, {"query": "a"}), (SEARCH, {"query": "b"})],
            docs={"b": [doc("B text.", "data/b.md")]}, pieces=("Ok.",))
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.reply == "Ok."


def test_empty_search_plus_tool_call_calls_the_answer_model(run, make_runner):
    """Covers: AC-2 (wrong), EC-7. With a tool call too, the answer model is called."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("q", [(SEARCH, {"query": "unicorn"}), (BEV, BEV_ARGS)], runners=runners,
            docs={}, pieces=("Bring 2 cambros.",))
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.answered_by_model is True
    assert r.outcome.reply == "Bring 2 cambros."
    last = r.llm.stream_calls[0][-1].content
    assert "data/" not in last and ".md" not in last


def test_no_docs_reply_text_is_the_contract_text():
    """Covers: AC-2 (right), EC-7. NO_DOCS_REPLY is the exact contract string."""
    assert NO_DOCS_REPLY == ("I don't know based on the available Bay Laurel documents. "
                             "Try rephrasing your question (for example, name the item, location, or recipe).")


# ---------------------------------------------------------------- the answer messages (4.4)

def test_answer_messages_start_with_system_prompt_and_end_with_human(run, doc):
    """Covers: AC-4 (right), EC-14, 4.4. First message SystemMessage(FLOW_ANSWER_PROMPT), last a HumanMessage."""
    r = run("q", [(SEARCH, {"query": "x"})], docs={"x": [doc("Doc.", "data/a.md")]})
    msgs = r.llm.stream_calls[0]
    assert isinstance(msgs, list)
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == FLOW_ANSWER_PROMPT
    assert isinstance(msgs[-1], HumanMessage)


def test_answer_call_binds_no_tools_when_planner_is_separate(run, doc):
    """Covers: AC-4 (right), EC-13, 4.4. The answer model gets no bind_tools call."""
    r = run("q", [(SEARCH, {"query": "x"})], docs={"x": [doc("Doc.", "data/a.md")]},
            separate_planner=True)
    assert r.llm.bind_calls == []


def test_answer_model_is_called_at_most_once_per_turn(run, doc, make_runner):
    """Covers: NFR-5 (boundary). Many calls in the plan still give one stream call and one planner call."""
    runners = {BEV: make_runner("ok", "a"), REC: make_runner("ok", "b")}
    r = run("How do I make 4 gallons of lemonade, and which cambros for 6 gallons of iced tea?",
            [(SEARCH, {"query": "x"}), (SEARCH, {"query": "y"}), (BEV, BEV_ARGS), (REC, REC_ARGS)],
            runners=runners, docs={"x": [doc("X.", "data/x.md")], "y": [doc("Y.", "data/y.md")]})
    assert len(r.llm.stream_calls) == 1
    assert len(r.llm.bind_calls) == 1
    assert len(r.llm.invoke_calls) == 1


def test_every_tool_text_and_document_reaches_the_last_message(run, doc, make_runner):
    """Covers: AC-1 (right), 4.4. All tool texts and all deduplicated documents with sources are in the last message."""
    runners = {BEV: make_runner("ok", "TEXT-ONE"), REC: make_runner("ok", "TEXT-TWO")}
    r = run("What now?", [(BEV, BEV_ARGS), (REC, REC_ARGS), (SEARCH, {"query": "x"})],
            runners=runners, docs={"x": [doc("DOC-A", "data/a.md"), doc("DOC-B", "data/b.md")]})
    last = r.llm.stream_calls[0][-1].content
    for token in ("TEXT-ONE", "TEXT-TWO", "DOC-A", "data/a.md", "DOC-B", "data/b.md", "What now?"):
        assert token in last


# ---------------------------------------------------------------- EC-9 streaming

def test_on_token_receives_the_streamed_pieces_in_order(run, make_runner):
    """Covers: AC-3 (right), EC-9. Pieces 'Bring ', '2 ', 'cambros.' arrive as exactly three tokens;
    reply is their join."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=("Bring ", "2 ", "cambros."))
    assert r.tokens == ["Bring ", "2 ", "cambros."]
    assert r.outcome.reply == "Bring 2 cambros."
    assert r.outcome.history[-1] == {"role": "assistant", "content": "Bring 2 cambros."}


def test_reply_is_stripped_but_tokens_are_not(run, make_runner):
    """Covers: AC-3 (boundary), EC-9. Outer spaces and newlines streamed are kept for on_token but
    stripped from reply (and from the assistant history item)."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    pieces = ("  Bring ", "2 cambros.\n")
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=pieces)
    assert r.tokens == list(pieces)
    assert r.outcome.reply == "Bring 2 cambros."
    assert r.outcome.history[-1]["content"] == "Bring 2 cambros."


def test_on_token_none_works(run, make_runner):
    """Covers: AC-3 (boundary), EC-9. Streaming with no callback still gives the reply."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=("Bring ", "2 cambros."), on_token=None)
    assert r.outcome.reply == "Bring 2 cambros."


def test_first_piece_reaches_on_token_before_the_stream_finishes(run, make_runner):
    """Covers: AC-3 (right), NFR-5. True streaming: when the fake produces its 2nd and 3rd pieces,
    on_token has already received the earlier ones."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=("Bring ", "2 ", "cambros."))
    assert r.llm.tokens_seen_before_piece == [0, 1, 2]


def test_single_piece_stream(run, make_runner):
    """Covers: AC-3 (boundary), EC-9. A one-piece stream gives one token."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=("Done.",))
    assert r.tokens == ["Done."]
    assert r.outcome.reply == "Done."


def test_history_adds_user_and_assistant_items(run, make_runner):
    """Covers: AC-3 (right), EC-12. A streamed reply is recorded as the assistant item."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("  How many cambros?  ", [(BEV, BEV_ARGS)], runners=runners, pieces=("Two.",))
    assert r.outcome.history[-2:] == [{"role": "user", "content": "How many cambros?"},
                                      {"role": "assistant", "content": "Two."}]


@pytest.mark.parametrize("status", ["ok", "invalid", "error"])
def test_non_need_info_tools_never_pass_through(run, make_runner, status):
    """Covers: AC-2 (boundary), EC-6. Any status other than need_info is answered by the model."""
    runners = {BEV: make_runner(status, "text"), REC: make_runner("ok", "x")}
    r = run("q", [(BEV, BEV_ARGS)], runners=runners, pieces=("Answer.",))
    assert r.outcome.answered_by_model is True
    assert len(r.llm.stream_calls) == 1

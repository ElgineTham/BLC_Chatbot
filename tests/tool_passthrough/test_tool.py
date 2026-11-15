"""Spec 023, section 6.1 (TOOL path): TOOL-1 to TOOL-11; AC-1, AC-2, AC-3, AC-8.

Unit: scripted fake models, fake store, fake runners.
"""
import pytest

from blc.flow import FAILED_TOOL_STATUSES, REPLY_SEPARATOR, TOOL_FAILED_REPLY

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
H = "Hot cups: 60 for 40 guests (40 guests plus 20 extras)."
# The question holds every number the plans use, so the spec 021 argument check never retries.
Q = "How many cambros for 6 gallons of iced tea, and how do I make 4 gallons of lemonade?"
BEV_ARGS = {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}
REC_ARGS = {"recipe": "lemonade", "gallons": 4}


def test_tool_1_single_ok_text_is_the_reply_word_for_word(run, make_runner):
    """Covers: AC-1 (right), TOOL-1. Reply is exactly H; on_token once; no model call; answered_by_model False."""
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == H
    assert r.tokens == [H]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_tool_1_history_gets_the_same_reply(run, make_runner):
    """Covers: AC-1 (right), TOOL-1. The assistant history item equals the reply."""
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.history[-1] == {"role": "assistant", "content": H}
    assert r.outcome.history[-2]["role"] == "user"


def test_tool_path_does_not_search(run, make_runner):
    """Covers: AC-1 (right), TOOL-1. Tools only: the store is not touched."""
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.store.calls == []


def test_tool_2_inner_newlines_kept_outer_whitespace_stripped(run, make_runner):
    """Covers: AC-1 (boundary), AC-2 (boundary), TOOL-2. Inner newlines survive; trailing newline is stripped."""
    runners = {BEV: make_runner("ok", "Line one.\nLine two.\n"), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == "Line one.\nLine two."
    assert r.outcome.history[-1]["content"] == "Line one.\nLine two."


def test_tool_3_two_texts_joined_with_blank_line_in_plan_order(run, make_runner):
    """Covers: AC-2 (right), TOOL-3. 'A.' then 'B\\nC.' join with a blank line; inner newline kept."""
    runners = {BEV: make_runner("ok", "A."), REC: make_runner("ok", "B\nC.")}
    r = run(Q, [(BEV, BEV_ARGS), (REC, REC_ARGS)], runners=runners)
    assert r.outcome.reply == "A.\n\nB\nC."
    assert r.llm.stream_calls == []


def test_tool_3_order_follows_the_plan_not_the_tool_name(run, make_runner):
    """Covers: AC-2 (boundary), TOOL-3. Reversing the plan reverses the texts."""
    runners = {BEV: make_runner("ok", "A."), REC: make_runner("ok", "B\nC.")}
    r = run(Q, [(REC, REC_ARGS), (BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == "B\nC.\n\nA."


def test_tool_4_two_need_info_texts_joined(run, make_runner):
    """Covers: AC-2 (right), AC-11, TOOL-4. need_info texts are joined with a blank line, not a single newline."""
    runners = {BEV: make_runner("need_info", "Which drink?"), REC: make_runner("need_info", "How many guests?")}
    r = run(Q, [(BEV, {}), (REC, {})], runners=runners)
    assert r.outcome.reply == "Which drink?\n\nHow many guests?"
    assert r.tokens == ["Which drink?\n\nHow many guests?"]
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_tool_5_ok_and_need_info_both_shown(run, make_runner):
    """Covers: AC-1 (right), AC-2 (right), TOOL-5. ok H then need_info: both texts, plan order, no model call."""
    runners = {BEV: make_runner("ok", H), REC: make_runner("need_info", "Which drink?")}
    r = run(Q, [(BEV, BEV_ARGS), (REC, {})], runners=runners)
    assert r.outcome.reply == H + "\n\nWhich drink?"
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


def test_tool_6_invalid_status_shows_friendly_sentence(run, make_runner):
    """Covers: AC-3 (right), TOOL-6. An invalid result is replaced by TOOL_FAILED_REPLY; raw text never reaches on_token."""
    raw = 'invalid request: gallons missing. Expected arguments: {"item": "cambros"}'
    runners = {BEV: make_runner("invalid", raw), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == TOOL_FAILED_REPLY
    assert all("Expected arguments" not in t for t in r.tokens)
    assert "Expected arguments" not in r.outcome.reply
    assert r.llm.stream_calls == []
    assert r.outcome.tools[0].status == "invalid"
    assert r.outcome.tools[0].text == raw


def test_tool_7_runner_exception_shows_friendly_sentence(run, make_runner):
    """Covers: AC-3 (wrong), TOOL-7. A runner raising ValueError gives status error; the user sees the sentence,
    the outcome still records 'error: bad'."""
    runners = {BEV: make_runner(raises=ValueError("bad")), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == TOOL_FAILED_REPLY
    assert r.tokens == [TOOL_FAILED_REPLY]
    assert r.outcome.tools[0].status == "error"
    assert r.outcome.tools[0].text == "error: bad"


def test_tool_8_sentence_appears_once_at_first_failed_place(run, make_seq_runner):
    """Covers: AC-3 (boundary), TOOL-8. ok 'A.', then invalid, then error: 'A.' + blank line + sentence, once."""
    runner = make_seq_runner(("ok", "A."), ("invalid", "raw invalid"), ("error", "error: raw"))
    runners = {BEV: runner, REC: runner}
    r = run(Q, [(BEV, BEV_ARGS), (BEV, BEV_ARGS), (BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == "A.\n\n" + TOOL_FAILED_REPLY
    assert r.outcome.reply.count(TOOL_FAILED_REPLY) == 1
    assert "raw" not in r.outcome.reply
    assert [t.status for t in r.outcome.tools] == ["ok", "invalid", "error"]


def test_tool_8_failed_first_then_ok_keeps_position(run, make_seq_runner):
    """Covers: AC-3 (boundary), TOOL-8. The sentence sits where the first failed result was, before a later ok text."""
    runner = make_seq_runner(("error", "error: x"), ("ok", "B."))
    r = run(Q, [(BEV, BEV_ARGS), (BEV, BEV_ARGS)], runners={BEV: runner, REC: runner})
    assert r.outcome.reply == TOOL_FAILED_REPLY + "\n\nB."


@pytest.mark.parametrize("status,text", [
    ("not_on_menu", "mango tea is not on the beverage menu."),
    ("no_recipe", "There is no recipe called pancakes."),
    ("something_else", "Some other status text."),
])
def test_tool_9_other_statuses_show_their_text(run, make_runner, status, text):
    """Covers: AC-3 (wrong), TOOL-9. Statuses outside FAILED_TOOL_STATUSES are shown verbatim, no model call."""
    runners = {BEV: make_runner(status, text), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == text
    assert TOOL_FAILED_REPLY not in r.outcome.reply
    assert r.llm.stream_calls == []


def test_tool_10_works_without_on_token(run, make_runner):
    """Covers: AC-1 (boundary), TOOL-10. on_token=None: reply unchanged."""
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners, on_token=None)
    assert r.outcome.reply == H
    assert r.llm.stream_calls == []


def test_tool_11_constants_match_contract():
    """Covers: AC-8 (right), TOOL-11. Constants equal the spec's section 3 values."""
    assert TOOL_FAILED_REPLY == ("I couldn't work that out. "
                                 "Try naming the drink and the number of guests or gallons.")
    assert REPLY_SEPARATOR == "\n\n"
    assert tuple(FAILED_TOOL_STATUSES) == ("invalid", "error")


def test_tool_path_planner_called_once(run, make_runner):
    """Covers: AC-8 (boundary). A clean tool turn costs one planner call and no answer call."""
    runners = {BEV: make_runner("ok", H), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert len(r.llm.invoke_calls) == 1
    assert r.llm.stream_calls == []


def test_ok_text_with_outer_spaces_is_stripped_in_reply(run, make_runner):
    """Covers: AC-1 (boundary). reply has outer whitespace stripped even on the tool path."""
    runners = {BEV: make_runner("ok", "  " + H + "  "), REC: make_runner("ok", "x")}
    r = run(Q, [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.reply == H

"""Spec 030 section 6.3 ANSWER-1 to ANSWER-6 (AC-4 to AC-8). Unit: scripted fake models, fake store.

The tool runner is injected from run_food_tool(args, rules) with the spec 029 Appendix A rules in tmp_path,
except in the tests of the default runner, which point FOOD_RULES_FILE at that copy.
"""
from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import blc.flow as flow_pkg
from blc.flow import (DEFAULT_TOOL_RUNNERS, REPLY_SEPARATOR, TOOL_FAILED_REPLY, ToolOutput, invented_numbers)
from blc.tools.food_tools import run_food_tool

FOOD = "calculate_food_item"
BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

Q_FORKS = "How many forks do I need for 70 guests?"
FORKS = {"item": "forks", "guests": 70}
NAP_LUNCH = {"item": "dinner napkins", "meal": "lunch"}


def _word(text, w):
    return re.search(rf"\b{w}\b", text) is not None


# ---------------------------------------------------------------- AC-4 default runner

def test_default_runner_keys_are_exactly_the_three():
    """Covers: AC-4 (right), ANSWER-1. Keys are the bev, recipe and food names plus (spec 043) the serving
    utensils tool; every value callable."""
    assert set(DEFAULT_TOOL_RUNNERS) == {BEV, REC, FOOD, "calculate_serving_utensils", "calculate_always_items"}
    assert all(callable(v) for v in DEFAULT_TOOL_RUNNERS.values())


@pytest.mark.parametrize("args", [
    {"item": "forks", "guests": 70},
    {"item": "small plates", "guests": 1},
    {"item": "dinner napkins", "meal": "lunch"},
    {"item": "cocktail napkins", "meal": "lunch"},
])
def test_default_food_runner_matches_run_food_tool_ok(args, rules, rules_path, point_rules_file_at):
    """Covers: AC-4 (right), ANSWER-1. The default food runner returns ToolOutput(status, text) equal to
    run_food_tool's for the same arguments (ok results)."""
    point_rules_file_at(rules_path)
    out = DEFAULT_TOOL_RUNNERS[FOOD](args)
    expected = run_food_tool(args, rules)
    assert isinstance(out, ToolOutput)
    assert expected.status == "ok"
    assert (out.status, out.text) == (expected.status, expected.text)


def test_default_food_runner_need_info(rules, rules_path, point_rules_file_at):
    """Covers: AC-4 (wrong), ANSWER-1. A need_info result (no guests) passes through status and text."""
    point_rules_file_at(rules_path)
    args = {"item": "forks"}
    out = DEFAULT_TOOL_RUNNERS[FOOD](args)
    expected = run_food_tool(args, rules)
    assert expected.status == "need_info"
    assert (out.status, out.text) == (expected.status, expected.text)


def test_default_food_runner_invalid(rules, rules_path, point_rules_file_at):
    """Covers: AC-4 (wrong), ANSWER-1. An invalid result (unknown item) passes through status and text."""
    point_rules_file_at(rules_path)
    args = {"item": "chairs", "guests": 10}
    out = DEFAULT_TOOL_RUNNERS[FOOD](args)
    expected = run_food_tool(args, rules)
    assert expected.status == "invalid"
    assert (out.status, out.text) == (expected.status, expected.text)


def test_importing_blc_flow_reads_no_food_rules_file():
    """Covers: AC-4 (right). A fresh interpreter that imports blc.flow opens no food.json (audit hook)."""
    src = Path(flow_pkg.__file__).resolve().parents[2]
    root = src.parent
    code = textwrap.dedent(
        """
        import sys
        opened = []
        def hook(event, args):
            if event == "open" and args and isinstance(args[0], (str, bytes)):
                p = args[0].decode() if isinstance(args[0], bytes) else args[0]
                if p.endswith("food.json"):
                    opened.append(p)
        sys.addaudithook(hook)
        import blc.flow
        print("OPENED:" + repr(opened))
        """
    )
    import os
    env = {**os.environ, "PYTHONPATH": str(src) + os.pathsep + str(root / "scripts")}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "OPENED:[]" in out.stdout, out.stdout


# ---------------------------------------------------------------- AC-5 TOOL path

def test_answer_1_count_reply_is_the_tool_text(run, food_runner):
    """Covers: AC-5 (right), ANSWER-1. {forks, 70}: reply equals the tool's text and has 120; the answer model
    is never called; on_token gets the text once."""
    r = run(Q_FORKS, [[(FOOD, FORKS)]])
    text = run_food_tool(FORKS, food_runner.rules).text
    assert r.outcome.plan.route == "TOOL"
    assert r.outcome.reply == text
    assert "120" in r.outcome.reply
    assert r.outcome.answered_by_model is False
    assert r.llm.stream_calls == []
    assert r.tokens == [text]
    assert food_runner.calls == [FORKS]


def test_answer_1_food_call_does_not_search(run):
    """Covers: AC-5 (right), ANSWER-1. A food-only plan never touches the store."""
    r = run(Q_FORKS, [[(FOOD, FORKS)]])
    assert r.store.calls == []


def test_answer_2_napkin_yes_reply(run, food_runner):
    """Covers: AC-5 (right), ANSWER-2. Dinner napkins for lunch: reply equals the tool's text with the whole
    word 'yes'; no model call."""
    r = run("Do I need dinner napkins for a lunch?", [[(FOOD, NAP_LUNCH)]])
    text = run_food_tool(NAP_LUNCH, food_runner.rules).text
    assert r.outcome.reply == text
    assert _word(r.outcome.reply, "yes")
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert r.tokens == [text]


def test_answer_2_napkin_no_reply(run, food_runner):
    """Covers: AC-5 (boundary), ANSWER-2. Cocktail napkins for lunch is a 'no' answer, still the tool's text
    word for word, no model call."""
    args = {"item": "cocktail napkins", "meal": "lunch"}
    r = run("Do I need cocktail napkins for a lunch?", [[(FOOD, args)]])
    text = run_food_tool(args, food_runner.rules).text
    assert r.outcome.reply == text
    assert _word(r.outcome.reply, "no")
    assert r.llm.stream_calls == []


def test_answer_3_need_info_reply_is_the_question(run, food_runner):
    """Covers: AC-5 (wrong), ANSWER-3. Dinner napkins with no meal: reply equals the tool's need_info text, a
    question ending '?' that mentions 'meal'; no model call."""
    args = {"item": "dinner napkins"}
    r = run("Do I need dinner napkins?", [[(FOOD, args)]])
    text = run_food_tool(args, food_runner.rules).text
    assert r.outcome.tools[0].status == "need_info"
    assert r.outcome.reply == text
    assert r.outcome.reply.strip().endswith("?")
    assert "meal" in r.outcome.reply
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert r.tokens == [text]


def test_need_info_history_gets_the_question(run, food_runner):
    """Covers: AC-5 (boundary), ANSWER-3. The assistant history item is the tool's question."""
    args = {"item": "forks"}
    text = run_food_tool(args, food_runner.rules).text
    r = run("How many forks do I need?", [[(FOOD, args)]])
    assert r.outcome.history[-1] == {"role": "assistant", "content": text}


def test_two_food_calls_replies_are_both_texts_without_the_model(run, food_runner):
    """Covers: AC-5 (right), extra. Knives and forks for 60 guests: both tool texts, nothing from the model."""
    a, b = {"item": "knives", "guests": 60}, {"item": "forks", "guests": 60}
    r = run("How many knives and forks for 60 guests?", [[(FOOD, a), (FOOD, b)]])
    ta, tb = (run_food_tool(x, food_runner.rules).text for x in (a, b))
    assert ta in r.outcome.reply and tb in r.outcome.reply
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


# ---------------------------------------------------------------- AC-6 invalid

def test_answer_4_invalid_shows_the_friendly_sentence(run, food_runner):
    """Covers: AC-6 (wrong), ANSWER-4. {chairs, 10}: reply is TOOL_FAILED_REPLY; the tool's raw invalid text
    is in neither the reply nor on_token."""
    args = {"item": "chairs", "guests": 10}
    r = run("How many chairs do I need for 10 guests?", [[(FOOD, args)]])
    raw = run_food_tool(args, food_runner.rules).text
    assert raw.strip()
    assert r.outcome.tools[0].status == "invalid"
    assert r.outcome.reply == TOOL_FAILED_REPLY
    assert raw not in r.outcome.reply
    assert all(raw not in piece for piece in r.tokens)
    assert TOOL_FAILED_REPLY in "".join(r.tokens)
    assert r.llm.stream_calls == []


def test_valid_call_never_shows_the_failed_reply(run):
    """Covers: AC-6 (right), ANSWER-4. An ok result is not replaced by TOOL_FAILED_REPLY."""
    r = run(Q_FORKS, [[(FOOD, FORKS)]])
    assert TOOL_FAILED_REPLY not in r.outcome.reply


# ---------------------------------------------------------------- AC-7 invented numbers

Q_NO_NUMBER = "How many forks do I need?"


def test_invented_guests_is_flagged():
    """Covers: AC-7 (wrong), ANSWER-5. guests 100 with no number in the question is invented."""
    assert invented_numbers(FOOD, {"item": "forks", "guests": 100}, Q_NO_NUMBER) == {"guests": (100,)}


def test_guests_in_question_is_accepted():
    """Covers: AC-7 (right), ANSWER-5. guests 70 that the question gave is not invented."""
    assert invented_numbers(FOOD, FORKS, Q_FORKS) == {}


def test_guests_in_history_is_accepted():
    """Covers: AC-7 (right), ANSWER-5. A number in an earlier turn (the history) counts as given."""
    hist = [{"role": "user", "content": "How many large plates for 100 guests?"},
            {"role": "assistant", "content": "Large plates: 150 (100 guests + 50 extra)"}]
    assert invented_numbers(FOOD, {"item": "forks", "guests": 100}, "And forks?", hist) == {}


def test_guests_spelled_out_is_accepted():
    """Covers: AC-7 (right). A spelled-out number in the question counts as given."""
    q = "How many small plates for fifty guests?"
    assert invented_numbers(FOOD, {"item": "small plates", "guests": 50}, q) == {}


def test_guests_spelled_out_in_history_is_accepted():
    """Covers: AC-7 (right). A spelled-out number in the history counts as given."""
    hist = [{"role": "user", "content": "We have sixty guests."}]
    assert invented_numbers(FOOD, {"item": "forks", "guests": 60}, "How many forks?", hist) == {}


def test_guests_one_is_always_accepted():
    """Covers: AC-7 (boundary), ANSWER-5. guests 1 is accepted even when no 1 is in the text."""
    assert invented_numbers(FOOD, {"item": "forks", "guests": 1}, Q_NO_NUMBER) == {}


def test_item_and_meal_are_never_flagged():
    """Covers: AC-7 (boundary), ANSWER-5. Numbers inside item or meal values are never reported; no guests
    means nothing to check."""
    assert invented_numbers(FOOD, {"item": "forks 999", "meal": "lunch 888"}, Q_NO_NUMBER) == {}
    assert invented_numbers(FOOD, {"item": "dinner napkins", "meal": "lunch"}, "Do I need dinner napkins?") == {}


def test_only_guests_key_is_reported():
    """Covers: AC-7 (wrong), ANSWER-5. With an invented guests next to item and meal, only guests is a key."""
    r = invented_numbers(FOOD, {"item": "dinner napkins", "meal": "lunch", "guests": 90}, "Dinner napkins for lunch?")
    assert set(r) == {"guests"} and r["guests"] == (90,)


def test_answer_5_twice_invented_value_is_dropped(run, food_runner):
    """Covers: AC-7 (wrong), ANSWER-5. A planner that twice sends guests 100: retried, rejected names the food
    call, the tool runs without guests, and the reply is the need_info question with no invented number."""
    bad = {"item": "forks", "guests": 100}
    r = run(Q_NO_NUMBER, [[(FOOD, bad)], [(FOOD, bad)]])
    o = r.outcome
    assert len(r.llm.invoke_calls) == 2
    assert o.retried is True
    assert [rc.name for rc in o.rejected] == [FOOD]
    assert o.rejected[0].invented == {"guests": (100,)}
    assert food_runner.calls == [{"item": "forks"}]
    assert "guests" not in o.tools[0].args
    assert o.tools[0].status == "need_info"
    assert o.reply == run_food_tool({"item": "forks"}, food_runner.rules).text
    assert "guests" in o.reply and o.reply.strip().endswith("?")
    assert "100" not in o.reply and "200" not in o.reply
    assert r.llm.stream_calls == []


def test_answer_5_retry_fixes_it(run, food_runner):
    """Covers: AC-7 (right), ANSWER-5. First plan invents guests, the second does not: retried, the tool runs
    on the second plan."""
    good = {"item": "forks"}
    r = run(Q_NO_NUMBER, [[(FOOD, {"item": "forks", "guests": 100})], [(FOOD, good)]])
    assert r.outcome.retried is True
    assert food_runner.calls == [good]
    assert r.outcome.plan.calls[0].args == good


def test_valid_guests_does_not_retry(run):
    """Covers: AC-7 (right), ANSWER-5. A guests value the user gave: one planner call, retried False."""
    r = run(Q_FORKS, [[(FOOD, FORKS)]])
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False and r.outcome.rejected == ()


def test_guests_from_history_does_not_retry(run):
    """Covers: AC-7 (right), FT-6 shape. guests 60 said in an earlier user turn: no retry, the runner gets it."""
    hist = [{"role": "user", "content": "We have 60 guests at the lunch. Where are the muffins kept?"},
            {"role": "assistant", "content": "On the metal rack in the service room."}]
    args = {"item": "forks", "guests": 60}
    r = run("How many forks do I need?", [[(FOOD, args)]], history=hist)
    assert r.outcome.retried is False
    assert r.runners[FOOD].calls == [args]


# ---------------------------------------------------------------- AC-8 BOTH

def test_answer_6_both_reply_order_and_model_isolation(run, doc, text_of, food_runner):
    """Covers: AC-8 (right), ANSWER-6. Food call plus a search with chunks: reply is tool text +
    REPLY_SEPARATOR + the model's answer; the tool part reaches on_token first, before stream; no message to
    the answer model holds the tool's text, 'Forks' or '120'."""
    q = "Where are the forks kept, and how many do I need for 70 guests?"
    query = "where are the forks kept"
    docs = {query: [doc("Cutlery is on the rack by the service door.", "data/food.md")]}
    r = run(q, [[(SEARCH, {"query": query}), (FOOD, FORKS)]], docs=docs, pieces=("Kept on ", "the rack."))
    tool_text = run_food_tool(FORKS, food_runner.rules).text
    assert r.outcome.plan.route == "BOTH"
    assert r.outcome.reply == tool_text + REPLY_SEPARATOR + "Kept on the rack."
    assert r.outcome.answered_by_model is True
    assert len(r.llm.stream_calls) == 1
    assert r.tokens and r.tokens[0].startswith(tool_text)
    assert r.llm.tokens_at_stream and r.llm.tokens_at_stream[0] >= 1
    sent = text_of(r.llm.stream_calls[0])
    assert tool_text not in sent
    assert "Forks" not in sent and "120" not in sent


def test_both_tool_part_is_not_repeated_by_the_model_pieces(run, doc, food_runner):
    """Covers: AC-8 (boundary), ANSWER-6. The tool text appears once in the reply."""
    query = "where are the forks kept"
    docs = {query: [doc("Cutlery is on the rack.", "data/food.md")]}
    r = run("Where are the forks kept, and how many for 70 guests?", [[(SEARCH, {"query": query}), (FOOD, FORKS)]],
            docs=docs, pieces=("Kept on the rack.",))
    tool_text = run_food_tool(FORKS, food_runner.rules).text
    assert r.outcome.reply.count(tool_text) == 1


def test_both_with_need_info_food_call_keeps_question_first(run, doc, food_runner):
    """Covers: AC-8 (boundary), extra. A need_info food result with a search that finds chunks: the question is
    first in the reply, then the separator, then the model's answer."""
    query = "where are the forks kept"
    docs = {query: [doc("Cutlery is on the rack.", "data/food.md")]}
    args = {"item": "forks"}
    r = run("Where are the forks kept, and how many do I need?", [[(SEARCH, {"query": query}), (FOOD, args)]],
            docs=docs, pieces=("On the rack.",))
    text = run_food_tool(args, food_runner.rules).text
    assert r.outcome.reply == text + REPLY_SEPARATOR + "On the rack."
    assert text not in "\n".join(str(m.content) for m in r.llm.stream_calls[0])


def test_both_with_invalid_food_shows_failed_reply_not_raw_text(run, doc, food_runner):
    """Covers: AC-6 (boundary), AC-8 (wrong), extra. Food invalid plus a search: TOOL_FAILED_REPLY is shown,
    the raw invalid text is not."""
    query = "where are the chairs kept"
    docs = {query: [doc("Chairs are in the back.", "data/food.md")]}
    args = {"item": "chairs", "guests": 10}
    q = "Where are the chairs kept, and how many do I need for 10 guests?"
    r = run(q, [[(SEARCH, {"query": query}), (FOOD, args)]], docs=docs, pieces=("In the back.",))
    raw = run_food_tool(args, food_runner.rules).text
    assert TOOL_FAILED_REPLY in r.outcome.reply
    assert raw not in r.outcome.reply

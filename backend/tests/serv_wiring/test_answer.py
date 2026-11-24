"""Spec 043 section 6.4 ANSWER-1 to ANSWER-5 (AC-4 to AC-7). Unit: scripted fake models, fake store.

The serving runner is injected from run_serv_tool(args, rules) with the spec 042 Appendix A rules in tmp_path,
except in the tests of the default runner, which point SERV_RULES_FILE at that copy.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import blc.flow as flow_pkg
from blc.flow import DEFAULT_TOOL_RUNNERS, REPLY_SEPARATOR, TOOL_FAILED_REPLY, ToolOutput
from blc.tools.serv_tools import run_serv_tool

SERV = "calculate_serving_utensils"
FOOD = "calculate_food_item"
BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

Q_CROISSANTS = "What serving utensils do I need for 3 dozen croissants?"
CROISSANTS = {"items": [{"food": "butter croissants", "qty": 3}]}
NO_QTY = {"items": [{"food": "butter croissants"}]}
LASAGNA = {"items": [{"food": "lasagna", "qty": 3}]}


# ---------------------------------------------------------------- AC-4 default runner

def test_default_runner_keys_are_exactly_the_four():
    """Covers: AC-4 (right), ANSWER-1. Keys are exactly the bev, recipe, food and serving names; all callable."""
    assert set(DEFAULT_TOOL_RUNNERS) == {BEV, REC, FOOD, SERV, "calculate_always_items"}
    assert all(callable(v) for v in DEFAULT_TOOL_RUNNERS.values())


@pytest.mark.parametrize("args", [
    {"items": [{"food": "butter croissants", "qty": 3}]},
    {"items": [{"food": "classic deli sandwiches", "qty": 51}, {"food": "bagels", "qty": 2, "unit": "dozen"}]},
    {"items": [{"food": "trail mix", "qty": 12}]},
])
def test_default_serv_runner_matches_run_serv_tool_ok(args, rules, rules_path, point_rules_file_at):
    """Covers: AC-4 (right), ANSWER-1. The default serving runner returns ToolOutput(status, text) equal to
    run_serv_tool's for the same arguments (ok results)."""
    point_rules_file_at(rules_path)
    out = DEFAULT_TOOL_RUNNERS[SERV](args)
    expected = run_serv_tool(args, rules=rules)
    assert isinstance(out, ToolOutput)
    assert expected.status == "ok"
    assert (out.status, out.text) == (expected.status, expected.text)


def test_default_serv_runner_need_info(rules, rules_path, point_rules_file_at):
    """Covers: AC-4 (wrong), ANSWER-1. A need_info result (no qty) passes through status and text."""
    point_rules_file_at(rules_path)
    out = DEFAULT_TOOL_RUNNERS[SERV](NO_QTY)
    expected = run_serv_tool(NO_QTY, rules=rules)
    assert expected.status == "need_info"
    assert (out.status, out.text) == (expected.status, expected.text)


def test_default_serv_runner_invalid(rules, rules_path, point_rules_file_at):
    """Covers: AC-4 (wrong), ANSWER-1. An invalid result (unknown food) passes through status and text."""
    point_rules_file_at(rules_path)
    out = DEFAULT_TOOL_RUNNERS[SERV](LASAGNA)
    expected = run_serv_tool(LASAGNA, rules=rules)
    assert expected.status == "invalid"
    assert (out.status, out.text) == (expected.status, expected.text)


def _fresh_interpreter(body):
    src = Path(flow_pkg.__file__).resolve().parents[2]
    root = src.parent
    env = {**os.environ, "PYTHONPATH": str(src) + os.pathsep + str(root / "scripts")}
    return subprocess.run([sys.executable, "-c", textwrap.dedent(body)], capture_output=True, text=True,
                          env=env, timeout=120)


def test_importing_blc_flow_opens_no_serving_rules_file():
    """Covers: AC-4 (right), ANSWER-5. A fresh interpreter that imports blc.flow opens no
    serving_utensils.json (audit hook)."""
    out = _fresh_interpreter(
        """
        import sys
        opened = []
        def hook(event, args):
            if event == "open" and args and isinstance(args[0], (str, bytes)):
                p = args[0].decode() if isinstance(args[0], bytes) else args[0]
                if p.endswith("serving_utensils.json"):
                    opened.append(p)
        sys.addaudithook(hook)
        import blc.flow
        print("OPENED:" + repr(opened))
        """)
    assert out.returncode == 0, out.stderr
    assert "OPENED:[]" in out.stdout, out.stdout


def test_importing_blc_flow_with_missing_rules_path_raises_nothing():
    """Covers: AC-4 (boundary), ANSWER-5. With SERV_RULES_FILE pointed at a missing path, importing blc.flow
    (no runner called) gives no error."""
    out = _fresh_interpreter(
        """
        import pathlib
        import blc.tools.serv_tools as st
        st.SERV_RULES_FILE = pathlib.Path("/nonexistent_dir_for_test/serving_utensils.json")
        import blc.flow
        print("IMPORTED")
        """)
    assert out.returncode == 0, out.stderr
    assert "IMPORTED" in out.stdout


# ---------------------------------------------------------------- AC-5 TOOL path

def test_answer_1_reply_is_the_tool_text(run, serv_runner, rules):
    """Covers: AC-5 (right), ANSWER-1. Croissants 3 dozen: reply equals the tool's text exactly; the answer
    model is never called; answered_by_model False; on_token gets the text once."""
    r = run(Q_CROISSANTS, [[(SERV, CROISSANTS)]])
    text = run_serv_tool(CROISSANTS, rules=rules).text
    assert r.outcome.plan.route == "TOOL"
    assert r.outcome.tools[0].status == "ok"
    assert r.outcome.reply == text
    assert "Small tongs: 4" in r.outcome.reply
    assert r.outcome.answered_by_model is False
    assert r.llm.stream_calls == []
    assert r.tokens == [text]
    assert serv_runner.calls == [CROISSANTS]


def test_serv_only_plan_never_searches(run):
    """Covers: AC-5 (right), ANSWER-1. A serving-only plan never touches the store."""
    r = run(Q_CROISSANTS, [[(SERV, CROISSANTS)]])
    assert r.store.calls == []


def test_answer_2_need_info_reply_is_the_question(run, rules):
    """Covers: AC-5 (wrong), ANSWER-2. Croissants with no qty: reply is the tool's need_info question (ends
    '?', has 'how many'); no model call."""
    r = run("What serving utensils for croissants?", [[(SERV, NO_QTY)]])
    text = run_serv_tool(NO_QTY, rules=rules).text
    assert r.outcome.tools[0].status == "need_info"
    assert r.outcome.reply == text
    assert r.outcome.reply.strip().endswith("?")
    assert "how many" in r.outcome.reply.lower()
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False
    assert r.tokens == [text]


def test_need_info_history_gets_the_question(run, rules):
    """Covers: AC-5 (boundary), ANSWER-2. The assistant history item is the tool's question."""
    text = run_serv_tool(NO_QTY, rules=rules).text
    r = run("What serving utensils for croissants?", [[(SERV, NO_QTY)]])
    assert r.outcome.history[-1] == {"role": "assistant", "content": text}


def test_ok_text_ends_with_counted_for_line_in_the_reply(run):
    """Covers: AC-5 (right), AC-9. The reply the user sees (the tool's text word for word) carries the
    'Counted for:' reading."""
    r = run(Q_CROISSANTS, [[(SERV, CROISSANTS)]])
    assert "Counted for:" in r.outcome.reply


def test_two_serving_calls_replies_are_both_texts_without_the_model(run, rules):
    """Covers: AC-5 (boundary), extra. Two serving calls: both tool texts appear, nothing from the model."""
    a = {"items": [{"food": "butter croissants", "qty": 3}]}
    b = {"items": [{"food": "classic deli sandwiches", "qty": 50}]}
    r = run("Utensils for 3 dozen croissants and 50 classic deli sandwiches?", [[(SERV, a), (SERV, b)]])
    ta, tb = (run_serv_tool(x, rules=rules).text for x in (a, b))
    assert ta in r.outcome.reply and tb in r.outcome.reply
    assert r.llm.stream_calls == []
    assert r.outcome.answered_by_model is False


# ---------------------------------------------------------------- AC-6 invalid

def test_answer_3_invalid_shows_the_friendly_sentence(run, rules):
    """Covers: AC-6 (wrong), ANSWER-3. Food 'lasagna', qty 3: reply is TOOL_FAILED_REPLY; the tool's raw
    invalid text is in neither the reply nor on_token."""
    r = run("Utensils for 3 lasagna?", [[(SERV, LASAGNA)]])
    raw = run_serv_tool(LASAGNA, rules=rules).text
    assert raw.strip()
    assert r.outcome.tools[0].status == "invalid"
    assert r.outcome.reply == TOOL_FAILED_REPLY
    assert raw not in r.outcome.reply
    assert all(raw not in piece for piece in r.tokens)
    assert TOOL_FAILED_REPLY in "".join(r.tokens)
    assert r.llm.stream_calls == []


def test_valid_call_never_shows_the_failed_reply(run):
    """Covers: AC-6 (right), ANSWER-3. An ok result is not replaced by TOOL_FAILED_REPLY."""
    r = run(Q_CROISSANTS, [[(SERV, CROISSANTS)]])
    assert TOOL_FAILED_REPLY not in r.outcome.reply


def test_invalid_unit_shows_the_failed_reply(run, rules):
    """Covers: AC-6 (boundary), extra. A unit mismatch (bags for a dozen food) is invalid too: friendly
    sentence only."""
    args = {"items": [{"food": "butter croissants", "qty": 3, "unit": "bags"}]}
    r = run("Utensils for 3 bags of croissants?", [[(SERV, args)]])
    assert r.outcome.tools[0].status == "invalid"
    assert r.outcome.reply == TOOL_FAILED_REPLY


# ---------------------------------------------------------------- AC-7 BOTH

def test_answer_4_both_reply_order_and_model_isolation(run, doc, text_of, rules):
    """Covers: AC-7 (right), ANSWER-4. Serving call plus a search that finds a chunk: reply is tool text +
    REPLY_SEPARATOR + the model's answer; the tool part reaches on_token first, before stream; no message to
    the answer model holds the tool's text."""
    q = "Where are the scones kept, and what utensils for 3 dozen croissants?"
    query = "where are the scones kept"
    docs = {query: [doc("Scones are on the metal rack.", "data/food.md")]}
    r = run(q, [[(SEARCH, {"query": query}), (SERV, CROISSANTS)]], docs=docs, pieces=("On the ", "rack."))
    tool_text = run_serv_tool(CROISSANTS, rules=rules).text
    assert r.outcome.plan.route == "BOTH"
    assert r.outcome.reply == tool_text + REPLY_SEPARATOR + "On the rack."
    assert r.outcome.answered_by_model is True
    assert len(r.llm.stream_calls) == 1
    assert r.tokens and r.tokens[0].startswith(tool_text)
    assert r.llm.tokens_at_stream and r.llm.tokens_at_stream[0] >= 1
    sent = text_of(r.llm.stream_calls[0])
    assert tool_text not in sent
    for line in tool_text.splitlines():
        if line.strip():
            assert line.strip() not in sent, line


def test_both_tool_text_appears_once(run, doc, rules):
    """Covers: AC-7 (boundary), ANSWER-4. The tool text appears once in the reply."""
    query = "where are the scones kept"
    docs = {query: [doc("Scones are on the rack.", "data/food.md")]}
    r = run("Where are the scones kept, and utensils for 3 dozen croissants?",
            [[(SEARCH, {"query": query}), (SERV, CROISSANTS)]], docs=docs, pieces=("On the rack.",))
    tool_text = run_serv_tool(CROISSANTS, rules=rules).text
    assert r.outcome.reply.count(tool_text) == 1


def test_both_with_need_info_keeps_question_first(run, doc, rules):
    """Covers: AC-7 (boundary), extra. A need_info serving result with a search that finds chunks: the question
    is first, then the separator, then the model's answer."""
    query = "where are the croissants kept"
    docs = {query: [doc("Croissants are on the rack.", "data/food.md")]}
    r = run("Where are the croissants kept, and what utensils do I need?",
            [[(SEARCH, {"query": query}), (SERV, NO_QTY)]], docs=docs, pieces=("On the rack.",))
    text = run_serv_tool(NO_QTY, rules=rules).text
    assert r.outcome.reply == text + REPLY_SEPARATOR + "On the rack."
    assert text not in "\n".join(str(m.content) for m in r.llm.stream_calls[0])


def test_both_with_invalid_serv_shows_failed_reply_not_raw_text(run, doc, rules):
    """Covers: AC-6 (boundary), AC-7 (wrong), extra. Serving invalid plus a search: TOOL_FAILED_REPLY is
    shown, the raw invalid text is not."""
    query = "where is the lasagna kept"
    docs = {query: [doc("Lasagna is in the freezer.", "data/food.md")]}
    r = run("Where is the lasagna kept, and utensils for 3 lasagna?",
            [[(SEARCH, {"query": query}), (SERV, LASAGNA)]], docs=docs, pieces=("In the freezer.",))
    raw = run_serv_tool(LASAGNA, rules=rules).text
    assert TOOL_FAILED_REPLY in r.outcome.reply
    assert raw not in r.outcome.reply

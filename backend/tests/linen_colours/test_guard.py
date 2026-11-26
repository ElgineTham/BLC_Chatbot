"""Spec 047 section 6.3 GUARD (AC-6): invented_numbers checks white_tables. Unit, scripted fake models."""
from __future__ import annotations

import pytest

from blc.flow import invented_numbers
from blc.tools.always_tools import run_always_tool

ALWAYS = "calculate_always_items"
Q5 = "White linens for 5 tables?"


def _white(value, question=Q5, history=None, about="tables"):
    return invented_numbers(ALWAYS, {"about": about, "white_tables": value}, question, history)


# ---------------------------------------------------------------- GUARD-1

def test_guard_1_number_in_question_accepted():
    """Covers: AC-6 (right), GUARD-1. white_tables 5 with '5 tables' in the question is not flagged."""
    assert _white(5) == {}


def test_guard_1_number_not_in_question_flagged():
    """Covers: AC-6 (wrong), GUARD-1. white_tables 6 is invented, reported under 'white_tables'."""
    assert _white(6) == {"white_tables": (6,)}


def test_guard_1_one_is_not_free():
    """Covers: AC-6 (boundary), GUARD-1. white_tables 1 is flagged when the question has no 1."""
    assert _white(1) == {"white_tables": (1,)}


def test_guard_1_zero_is_not_free():
    """Covers: AC-6 (boundary), GUARD-1. white_tables 0 is flagged when the question has no 0."""
    assert _white(0) == {"white_tables": (0,)}


# ---------------------------------------------------------------- GUARD-2

def test_guard_2_spelled_out_in_question():
    """Covers: AC-6 (right), GUARD-2. 'five' in the question lets white_tables 5 through."""
    assert _white(5, "White linens for five tables?") == {}


def test_guard_2_number_in_history():
    """Covers: AC-6 (right), GUARD-2. A 5 said only in the history lets white_tables 5 through."""
    history = [{"role": "user", "content": "We have 5 tables with white linens."}]
    assert _white(5, "How many white linens do I need?", history) == {}


def test_guard_2_history_number_flagged_without_history():
    """Covers: AC-6 (wrong), GUARD-2. The same 5 with no history is flagged."""
    assert _white(5, "How many white linens do I need?") == {"white_tables": (5,)}


def test_guard_2_one_given_in_question():
    """Covers: AC-6 (boundary), GUARD-2. 'White linens for 1 table?' with white_tables 1 is not flagged."""
    assert _white(1, "White linens for 1 table?") == {}


def test_guard_2_zero_given_in_question():
    """Covers: AC-6 (boundary), GUARD-2. 'White linens for 0 tables?' with white_tables 0 is not flagged."""
    assert _white(0, "White linens for 0 tables?") == {}


# ---------------------------------------------------------------- tables, drip_trays unchanged

def test_tables_and_white_each_checked_with_own_key():
    """Covers: AC-6 (wrong). Both invented: each reported under its own key."""
    args = {"about": "tables", "tables": 3, "white_tables": 7}
    assert invented_numbers(ALWAYS, args, "How many linens?") == {"tables": (3,), "white_tables": (7,)}


def test_valid_pair_not_flagged():
    """Covers: AC-6 (right). '3 tables with black linens and 2 with white' with tables 3, white_tables 2: {}."""
    q = "We have 3 tables with black linens and 2 with white linens. How many linens?"
    args = {"about": "tables", "tables": 3, "white_tables": 2}
    assert invented_numbers(ALWAYS, args, q) == {}


def test_only_white_invented_tables_ok():
    """Covers: AC-6 (boundary). Only the invented key is reported when tables is given and white_tables is not."""
    args = {"about": "tables", "tables": 3, "white_tables": 9}
    assert invented_numbers(ALWAYS, args, "Linens for 3 tables?") == {"white_tables": (9,)}


def test_tables_and_drip_trays_unchanged():
    """Covers: AC-6 (right). Tables and drip_trays handling is unchanged: flagged under their own keys, 1 and 0
    included."""
    q = "Always items?"
    assert invented_numbers(ALWAYS, {"about": "both", "tables": 1, "drip_trays": 0}, q) == {
        "tables": (1,), "drip_trays": (0,)}
    assert invented_numbers(ALWAYS, {"about": "both", "tables": 4, "drip_trays": 3}, "4 tables, 3 drip trays") == {}


def test_no_white_tables_nothing_flagged():
    """Covers: AC-6 (boundary). A call without white_tables, or with null, adds nothing to flag."""
    assert invented_numbers(ALWAYS, {"about": "tables"}, "How many linens?") == {}
    assert invented_numbers(ALWAYS, {"about": "tables", "white_tables": None}, "How many linens?") == {}


# ---------------------------------------------------------------- GUARD-3 full turn

def test_guard_3_twice_invented_white_tables_dropped(run):
    """Covers: AC-6 (wrong), GUARD-3. 'How many white linens?' with the planner twice sending white_tables 37:
    retried True; the final call has no white_tables; the reply asks how many tables."""
    bad = {"about": "tables", "white_tables": 37}
    r = run("How many white linens?", [[(ALWAYS, bad)], [(ALWAYS, bad)]])
    o = r.outcome
    assert len(r.llm.invoke_calls) == 2
    assert o.retried is True
    assert [rc.name for rc in o.rejected] == [ALWAYS]
    assert o.rejected[0].invented == {"white_tables": (37,)}
    final = o.plan.calls[0]
    assert final.name == ALWAYS
    assert final.args["about"] == "tables"
    assert "white_tables" not in final.args
    assert o.tools[0].status == "need_info"
    assert o.reply == run_always_tool({"about": "tables"}).text
    last = o.reply.strip().splitlines()[-1].lower()
    assert o.reply.strip().endswith("?")
    assert "how many" in last and "tables" in last
    assert "37" not in o.reply


def test_guard_3_retry_fixes_it(run):
    """Covers: AC-6 (right), GUARD-3. First plan invents white_tables, the second uses the user's number: the
    tool runs on the second plan."""
    good = {"about": "tables", "white_tables": 5}
    r = run(Q5, [[(ALWAYS, {"about": "tables", "white_tables": 37})], [(ALWAYS, good)]])
    assert r.outcome.retried is True
    assert r.outcome.plan.calls[0].args == good
    assert r.outcome.tools[0].status == "ok"
    assert r.outcome.reply == run_always_tool(good).text


def test_guard_3_valid_white_tables_does_not_retry(run):
    """Covers: AC-6 (right), GUARD-3. Extra: a white_tables the user gave: one planner call, nothing rejected."""
    r = run(Q5, [[(ALWAYS, {"about": "tables", "white_tables": 5})]])
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False and r.outcome.rejected == ()
    assert "White linens: 11" in r.outcome.reply


@pytest.mark.parametrize("bad_value", [1, 0])
def test_guard_3_one_and_zero_retry_in_full_turn(run, bad_value):
    """Covers: AC-6 (boundary), GUARD-3. Extra: an invented white_tables of 1 or 0 triggers the retry too."""
    bad = {"about": "tables", "white_tables": bad_value}
    r = run("How many white linens?", [[(ALWAYS, bad)], [(ALWAYS, bad)]])
    assert r.outcome.retried is True
    assert "white_tables" not in r.outcome.plan.calls[0].args

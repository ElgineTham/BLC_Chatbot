"""Spec 045 section 6.5 GUARD (AC-13, AC-14): invented numbers for the always tool. Unit: scripted fake models."""
from __future__ import annotations

import re

import pytest

from blc.flow import invented_numbers
from blc.tools.always_tools import run_always_tool

ALWAYS = "calculate_always_items"
SERV = "calculate_serving_utensils"
FOOD = "calculate_food_item"
Q4 = "Linens for 4 tables?"


def _tables(value, question=Q4, history=None, about="tables"):
    return invented_numbers(ALWAYS, {"about": about, "tables": value}, question, history)


# ---------------------------------------------------------------- GUARD-1

def test_guard_1_number_in_question_accepted():
    """Covers: AC-13 (right), GUARD-1. tables 4 with '4 tables' in the question is not flagged."""
    assert _tables(4) == {}


def test_guard_1_number_not_in_question_flagged():
    """Covers: AC-13 (wrong), GUARD-1. tables 5 is invented, reported under 'tables'."""
    assert _tables(5) == {"tables": (5,)}


def test_guard_1_one_is_not_free():
    """Covers: AC-13 (boundary), GUARD-1. tables 1 is flagged when the question has no 1."""
    assert _tables(1) == {"tables": (1,)}


def test_guard_1_zero_is_not_free():
    """Covers: AC-13 (boundary), GUARD-1. tables 0 is flagged when the question has no 0."""
    assert _tables(0) == {"tables": (0,)}


def test_guard_drip_trays_one_and_zero_flagged():
    """Covers: AC-13 (boundary). Extra: drip_trays 1 and 0 are flagged under 'drip_trays' too."""
    q = "Black napkins please"
    assert invented_numbers(ALWAYS, {"about": "drip_trays", "drip_trays": 1}, q) == {"drip_trays": (1,)}
    assert invented_numbers(ALWAYS, {"about": "drip_trays", "drip_trays": 0}, q) == {"drip_trays": (0,)}


# ---------------------------------------------------------------- GUARD-2

def test_guard_2_spelled_out_in_question():
    """Covers: AC-13 (right), GUARD-2. tables 4 with 'four tables' in the question is not flagged."""
    assert _tables(4, "Linens for four tables?") == {}


def test_guard_2_number_from_history():
    """Covers: AC-13 (right), GUARD-2. tables 6 said in an earlier turn is not flagged."""
    history = [{"role": "user", "content": "We have 6 tables."}]
    assert _tables(6, "How many black linens do I need?", history) == {}


def test_guard_2_history_number_flagged_without_history():
    """Covers: AC-13 (wrong), GUARD-2. The same 6 with no history is flagged."""
    assert _tables(6, "How many black linens do I need?") == {"tables": (6,)}


def test_guard_2_spelled_out_in_history():
    """Covers: AC-13 (right), GUARD-2. A spelled-out number in the history counts as given."""
    history = [{"role": "user", "content": "We have six tables."}]
    assert _tables(6, "Linens please?", history) == {}


def test_guard_2_one_given_in_question():
    """Covers: AC-13 (boundary), GUARD-2. 'Linens for 1 table?' with tables 1 is not flagged."""
    assert _tables(1, "Linens for 1 table?") == {}


def test_guard_2_spelled_one_given():
    """Covers: AC-13 (boundary). 'one' in the question lets tables 1 through."""
    assert _tables(1, "Linens for one table?") == {}


def test_guard_2_zero_given_in_question():
    """Covers: AC-13 (boundary). tables 0 with '0 tables' in the question is not flagged."""
    assert _tables(0, "Linens for 0 tables?") == {}


def test_guard_2_drip_trays_from_history_and_spelled():
    """Covers: AC-13 (right). drip_trays are checked against the question and history like tables."""
    history = [{"role": "user", "content": "There are two drip trays."}]
    args = {"about": "drip_trays", "drip_trays": 2}
    assert invented_numbers(ALWAYS, args, "Black napkins?", history) == {}
    assert invented_numbers(ALWAYS, args, "Black napkins?") == {"drip_trays": (2,)}


# ---------------------------------------------------------------- GUARD-3

def test_guard_3_drip_trays_invented():
    """Covers: AC-13 (wrong), GUARD-3. 'Black napkins please' with drip_trays 2 is flagged under 'drip_trays'."""
    result = invented_numbers(ALWAYS, {"about": "drip_trays", "drip_trays": 2}, "Black napkins please")
    assert result == {"drip_trays": (2,)}


@pytest.mark.parametrize("about", ["tables", "drip_trays", "both", "TABLES", "drip trays", "7", "", "linens"])
def test_guard_3_about_never_flagged(about):
    """Covers: AC-13 (boundary), GUARD-3. 'about' is never flagged, whatever its value."""
    assert invented_numbers(ALWAYS, {"about": about}, "What are the always items?") == {}
    result = invented_numbers(ALWAYS, {"about": about, "drip_trays": 2}, "Black napkins please")
    assert set(result) == {"drip_trays"}


def test_guard_3_numeric_about_not_flagged():
    """Covers: AC-13 (boundary). Even a numeric about value that is not in the question is not flagged."""
    assert invented_numbers(ALWAYS, {"about": 99}, "What are the always items?") == {}


def test_guard_both_invented_reported_under_own_keys():
    """Covers: AC-13 (wrong). Both numbers invented: each reported under its own key."""
    result = invented_numbers(ALWAYS, {"about": "both", "tables": 5, "drip_trays": 7}, "Always items?")
    assert result == {"tables": (5,), "drip_trays": (7,)}


def test_guard_one_valid_one_invented():
    """Covers: AC-13 (boundary). Only the invented number is reported."""
    result = invented_numbers(ALWAYS, {"about": "both", "tables": 4, "drip_trays": 7}, "Always for 4 tables?")
    assert result == {"drip_trays": (7,)}


def test_guard_no_numbers_nothing_to_check():
    """Covers: AC-13 (boundary). A call with only 'about' has nothing to flag."""
    assert invented_numbers(ALWAYS, {"about": "both"}, "What are the always items?") == {}


# ---------------------------------------------------------------- GUARD-4 full turn

Q_PURPLE = "How many purple napkins do I need?"


def test_guard_4_twice_invented_tables_dropped(run):
    """Covers: AC-13 (wrong), GUARD-4. The planner twice sends about tables, tables 1: retried True; the final
    call has about 'tables' and no tables key; the reply is the need_info question with bus tubs and towels
    and no '1' count."""
    bad = {"about": "tables", "tables": 1}
    r = run(Q_PURPLE, [[(ALWAYS, bad)], [(ALWAYS, bad)]])
    o = r.outcome
    assert len(r.llm.invoke_calls) == 2
    assert o.retried is True
    assert [rc.name for rc in o.rejected] == [ALWAYS]
    assert o.rejected[0].invented == {"tables": (1,)}
    final = o.plan.calls[0]
    assert final.name == ALWAYS
    assert final.args["about"] == "tables"
    assert "tables" not in final.args
    assert o.tools[0].status == "need_info"
    assert o.reply == run_always_tool({"about": "tables"}).text
    assert "Bus tubs" in o.reply and "Towels" in o.reply
    assert o.reply.strip().endswith("?")
    assert "how many" in o.reply.lower() and "tables" in o.reply.lower()
    assert not re.search(r"\b1\b", o.reply)
    assert r.llm.stream_calls == []
    assert o.answered_by_model is False


def test_guard_4_keeps_the_other_key(run):
    """Covers: AC-13 (boundary), GUARD-4. Only the invented key is removed: about 'both', tables 1 (invented)
    and drip_trays 3 (given) keeps drip_trays and asks for tables, listing the napkin count."""
    q = "Always items for 3 drip trays?"
    bad = {"about": "both", "tables": 1, "drip_trays": 3}
    r = run(q, [[(ALWAYS, bad)], [(ALWAYS, bad)]])
    final = r.outcome.plan.calls[0]
    assert final.args == {"about": "both", "drip_trays": 3}
    assert r.outcome.tools[0].status == "need_info"
    assert "Black napkins: 3" in r.outcome.reply
    assert "tables" in r.outcome.reply.lower().splitlines()[-1]


def test_guard_4_retry_fixes_it(run):
    """Covers: AC-13 (right), GUARD-4. The first plan invents tables, the second does not: retried, the tool
    runs on the second plan's arguments."""
    good = {"about": "tables", "tables": 4}
    r = run("Linens for 4 tables?", [[(ALWAYS, {"about": "tables", "tables": 9})], [(ALWAYS, good)]])
    assert r.outcome.retried is True
    assert r.outcome.plan.calls[0].args == good
    assert r.outcome.tools[0].status == "ok"
    assert r.outcome.reply == run_always_tool(good).text


def test_guard_4_valid_number_does_not_retry(run):
    """Covers: AC-13 (right), GUARD-4. A number the user gave: one planner call, retried False, nothing
    rejected."""
    r = run("Linens for 4 tables?", [[(ALWAYS, {"about": "tables", "tables": 4})]])
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False and r.outcome.rejected == ()


def test_guard_4_number_from_history_does_not_retry(run):
    """Covers: AC-13 (right), GUARD-4. A number said in an earlier user turn is accepted: no retry."""
    history = [{"role": "user", "content": "We have 6 tables."},
               {"role": "assistant", "content": "Noted."}]
    args = {"about": "tables", "tables": 6}
    r = run("How many black linens?", [[(ALWAYS, args)]], history=history)
    assert r.outcome.retried is False
    assert r.outcome.plan.calls[0].args == args


# ---------------------------------------------------------------- GUARD-5 (AC-14)

def test_guard_5_serving_qty_one_still_accepted():
    """Covers: AC-14 (right), GUARD-5. The serving tool still accepts qty 1 with no 1 in the question."""
    args = {"items": [{"food": "bagels", "qty": 1}]}
    assert invented_numbers(SERV, args, "What serving utensils do I need for bagels?") == {}


def test_guard_5_food_guests_still_flagged():
    """Covers: AC-14 (wrong), GUARD-5. A food call with guests 70 not in the question is flagged as before."""
    result = invented_numbers(FOOD, {"item": "forks", "guests": 70}, "How many forks do I need?")
    assert result == {"guests": (70,)}


def test_guard_5_food_guests_in_question_accepted():
    """Covers: AC-14 (right), GUARD-5. Extra: guests 70 that the question gave is not flagged."""
    assert invented_numbers(FOOD, {"item": "forks", "guests": 70}, "Forks for 70 guests?") == {}

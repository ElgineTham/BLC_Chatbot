"""Spec 043 section 6.5 INVENT-1 to INVENT-3 (AC-8). Unit: scripted fake models.

INVENT-3 names muffins and scones, which are not in the Appendix A test rules the unit rows must use, so it uses
the Appendix A foods bagels and croissants in the same shape (reported to the planner).
"""
from __future__ import annotations

import pytest

import serv_wiring_helpers as swh
from blc.flow import invented_numbers
from blc.tools.serv_tools import run_serv_tool

SERV = "calculate_serving_utensils"
Q_MUFFINS = "Utensils for 4 dozen muffins"
Q_NO_NUMBER = "What serving utensils do I need for muffins?"


def _call(items, question, history=None):
    return invented_numbers(SERV, {"items": items}, question, history)


# ---------------------------------------------------------------- INVENT-1

def test_qty_in_question_is_accepted():
    """Covers: AC-8 (right), INVENT-1. qty 4 that the question gave is not invented."""
    assert _call([{"food": "breakfast muffins", "qty": 4}], Q_MUFFINS) == {}


def test_qty_not_in_question_is_flagged():
    """Covers: AC-8 (wrong), INVENT-1. qty 48 (4 dozen turned into pieces by the model) is invented."""
    assert _call([{"food": "breakfast muffins", "qty": 48}], Q_MUFFINS) == {"qty": (48,)}


def test_qty_one_is_always_accepted():
    """Covers: AC-8 (boundary), INVENT-1. qty 1 is accepted even when no 1 is in the text."""
    assert _call([{"food": "breakfast muffins", "qty": 1}], Q_NO_NUMBER) == {}


def test_qty_spelled_out_is_accepted():
    """Covers: AC-8 (right), INVENT-1. qty 'four' with 'four dozen' in the question is not invented."""
    assert _call([{"food": "breakfast muffins", "qty": "four"}], "Utensils for four dozen muffins") == {}


def test_qty_number_for_spelled_out_question_is_accepted():
    """Covers: AC-8 (right), INVENT-1. qty 4 with 'four dozen' in the question counts as given."""
    assert _call([{"food": "breakfast muffins", "qty": 4}], "Utensils for four dozen muffins") == {}


def test_qty_from_history_is_accepted():
    """Covers: AC-8 (right), INVENT-1. qty 30 said in an earlier turn (H-LUNCH) is not invented."""
    q = "What serving utensils do I need for the classic deli sandwiches?"
    assert _call([{"food": "classic deli sandwiches", "qty": 30}], q, swh.H_LUNCH) == {}


def test_qty_from_history_is_flagged_without_the_history():
    """Covers: AC-8 (wrong), INVENT-1. The same qty 30 with no history is invented."""
    q = "What serving utensils do I need for the classic deli sandwiches?"
    assert _call([{"food": "classic deli sandwiches", "qty": 30}], q) == {"qty": (30,)}


def test_qty_spelled_out_in_history_is_accepted():
    """Covers: AC-8 (right), INVENT-1. A spelled-out number in the history counts as given."""
    hist = [{"role": "user", "content": "We have thirty guests."}]
    assert _call([{"food": "classic deli sandwiches", "qty": 30}], "Utensils for the deli sandwiches?", hist) == {}


def test_each_item_is_checked():
    """Covers: AC-8 (boundary), INVENT-1. One valid and one invented qty: only the invented value is reported,
    under the key 'qty'."""
    items = [{"food": "bagels", "qty": 2}, {"food": "butter croissants", "qty": 99}]
    assert _call(items, "Utensils for 2 dozen bagels and some croissants") == {"qty": (99,)}


def test_several_invented_values_are_all_reported():
    """Covers: AC-8 (boundary), INVENT-1. Two invented values from two items are both in the 'qty' entry."""
    items = [{"food": "bagels", "qty": 48}, {"food": "butter croissants", "qty": 99}]
    result = invented_numbers(SERV, {"items": items}, "Utensils for bagels and croissants")
    assert set(result) == {"qty"}
    assert set(result["qty"]) == {48, 99}


def test_items_without_qty_have_nothing_to_check():
    """Covers: AC-8 (boundary), INVENT-1. Items with no qty give no flag."""
    items = [{"food": "bagels"}, {"food": "butter croissants", "unit": "dozen"}]
    assert invented_numbers(SERV, {"items": items}, Q_NO_NUMBER) == {}


# ---------------------------------------------------------------- INVENT-2

@pytest.mark.parametrize("item", [
    {"food": "7 layer bars"},
    {"food": "7 layer bars", "unit": "dozen"},
    {"food": "bagels 999", "unit": "12 pack"},
    {"food": "7 layer bars", "qty": 4, "unit": "88"},
])
def test_food_and_unit_are_never_flagged(item):
    """Covers: AC-8 (boundary), INVENT-2. Numbers inside food or unit values are never reported."""
    assert _call([item], Q_MUFFINS) == {}


def test_only_the_qty_key_is_reported():
    """Covers: AC-8 (wrong), INVENT-2. With an invented qty next to an odd food and unit, only 'qty' is a key."""
    result = _call([{"food": "7 layer bars", "qty": 90, "unit": "dozen"}], "Utensils for 7 layer bars")
    assert set(result) == {"qty"} and result["qty"] == (90,)


def test_other_tools_are_unaffected():
    """Covers: AC-8 (boundary), extra. A food call with guests still reports under 'guests', not 'qty'."""
    result = invented_numbers("calculate_food_item", {"item": "forks", "guests": 100}, "How many forks?")
    assert result == {"guests": (100,)}


# ---------------------------------------------------------------- INVENT-3

def test_invent_3_twice_invented_qty_is_dropped_from_that_item_only(run, serv_runner, rules):
    """Covers: AC-8 (wrong), INVENT-3. The planner twice sends bagels qty 48 (invented) and croissants qty 2
    (given): retried; the final call keeps both items, the bagels without qty and the croissants with qty 2;
    the reply is the need_info question naming the bagels, with no '48'."""
    q = "Utensils for bagels and 2 dozen croissants?"
    bad = {"items": [{"food": "bagels", "qty": 48}, {"food": "butter croissants", "qty": 2}]}
    expected_args = {"items": [{"food": "bagels"}, {"food": "butter croissants", "qty": 2}]}
    r = run(q, [[(SERV, bad)], [(SERV, bad)]])
    o = r.outcome
    assert len(r.llm.invoke_calls) == 2
    assert o.retried is True
    assert [rc.name for rc in o.rejected] == [SERV]
    assert o.rejected[0].invented == {"qty": (48,)}
    final = o.plan.calls[0]
    assert final.name == SERV
    items = final.args["items"]
    assert len(items) == 2
    assert items[0]["food"] == "bagels" and "qty" not in items[0]
    assert items[1]["food"] == "butter croissants" and items[1]["qty"] == 2
    assert serv_runner.calls == [expected_args]
    assert o.tools[0].status == "need_info"
    assert o.reply == run_serv_tool(expected_args, rules=rules).text
    assert "bagels" in o.reply.lower() and o.reply.strip().endswith("?")
    assert "48" not in o.reply
    assert r.llm.stream_calls == []
    assert o.answered_by_model is False


def test_all_items_invented_all_qty_dropped(run, serv_runner, rules):
    """Covers: AC-8 (boundary), INVENT-3. Every item has an invented qty twice: all qty removed, the reply asks
    about both foods."""
    bad = {"items": [{"food": "bagels", "qty": 48}, {"food": "butter croissants", "qty": 96}]}
    r = run("Utensils for bagels and croissants?", [[(SERV, bad)], [(SERV, bad)]])
    o = r.outcome
    assert o.retried is True
    assert all("qty" not in i for i in o.plan.calls[0].args["items"])
    assert [i["food"] for i in o.plan.calls[0].args["items"]] == ["bagels", "butter croissants"]
    assert o.tools[0].status == "need_info"
    assert "bagels" in o.reply.lower() and "croissants" in o.reply.lower()
    assert "48" not in o.reply and "96" not in o.reply


def test_invent_3_retry_fixes_it(run, serv_runner):
    """Covers: AC-8 (right), INVENT-3. First plan invents qty, the second does not: retried, the tool runs on
    the second plan's arguments."""
    good = {"items": [{"food": "bagels", "qty": 2}]}
    r = run("Utensils for 2 dozen bagels?", [[(SERV, {"items": [{"food": "bagels", "qty": 24}]})], [(SERV, good)]])
    assert r.outcome.retried is True
    assert serv_runner.calls == [good]
    assert r.outcome.plan.calls[0].args == good
    assert r.outcome.tools[0].status == "ok"


def test_valid_qty_does_not_retry(run):
    """Covers: AC-8 (right), INVENT-3. A qty the user gave: one planner call, retried False, nothing rejected."""
    args = {"items": [{"food": "bagels", "qty": 2}]}
    r = run("Utensils for 2 dozen bagels?", [[(SERV, args)]])
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False and r.outcome.rejected == ()


def test_qty_from_history_does_not_retry(run, serv_runner):
    """Covers: AC-8 (right), FOLLOW-3 shape. qty 30 said in an earlier user turn: no retry, the runner gets it."""
    args = {"items": [{"food": "classic deli sandwiches", "qty": 30}]}
    r = run("What serving utensils do I need for the classic deli sandwiches?", [[(SERV, args)]],
            history=swh.H_LUNCH)
    assert r.outcome.retried is False
    assert serv_runner.calls == [args]

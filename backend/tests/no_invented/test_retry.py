"""Spec 021, AC-2 (retry and drop): EC-13 to EC-18 and EC-21.

Unit tests of run_planned_turn with scripted fake planner/answer models, a fake store and fake runners.
The fake model raises if the planner is called more often than scripted, so a third call fails a test.
"""
from __future__ import annotations

import re

from blc.flow import RejectedCall
from blc.planner import NO_INVENTED_RULE

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

Q60 = "For 60 guests of peach tea, how many cambros and cups"
BAD = {"item": "cambros", "drinks": ["peach tea"], "guests": 60, "gallons": [6]}
GOOD = {"item": "cambros", "drinks": ["peach tea"], "guests": 60}


def bev_calls(r):
    return r.runners[BEV].calls


# ---------------------------------------------------------------- EC-13

def test_ec13_nothing_invented_runs_first_plan(run):
    """Covers: AC-2 (right), EC-13, EC-21. One planner call, retried False, rejected empty, first_plan == plan."""
    r = run(Q60, [[(BEV, GOOD)]])
    o = r.outcome
    assert len(r.llm.invoke_calls) == 1
    assert o.retried is False
    assert o.rejected == ()
    assert o.first_plan == o.plan
    assert bev_calls(r) == [GOOD]


def test_ec13_numbers_from_history_do_not_trigger_retry(run):
    """Covers: AC-2 (right), EC-13. Numbers in the assistant's earlier reply count as given."""
    hist = [{"role": "user", "content": "How many gallons of coffee for 100 guests?"},
            {"role": "assistant", "content": "Coffee: 4 gallons for 100 guests."}]
    args = {"item": "cambros", "drinks": ["coffee"], "gallons": [4]}
    r = run("How many cambros for that?", [[(BEV, args)]], history=hist)
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False
    assert bev_calls(r) == [args]


def test_search_with_numbers_does_not_trigger_retry(run):
    """Covers: AC-2 (boundary), EC-11, EC-13. A search query with a number is never checked."""
    r = run("Where are the cambros?", [[(SEARCH, {"query": "where are the 9 cambros"})]])
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False
    assert r.outcome.rejected == ()


def test_non_numeric_value_does_not_trigger_retry(run):
    """Covers: AC-2 (boundary), EC-9, EC-13. 'lots' is the tool's problem, not a reason to retry."""
    args = {"item": "cambros", "drinks": ["peach tea"], "gallons": "lots"}
    r = run("How many cambros of peach tea", [[(BEV, args)]])
    assert len(r.llm.invoke_calls) == 1
    assert r.outcome.retried is False
    assert bev_calls(r) == [args]


# ---------------------------------------------------------------- EC-14

def test_ec14_retry_fixes_it(run, text_of):
    """Covers: AC-2 (right), EC-14, EC-21. Two planner calls; the second sees the rule, tool, argument, value."""
    r = run(Q60, [[(BEV, BAD)], [(BEV, GOOD)]])
    assert len(r.llm.invoke_calls) == 2
    first_contents = {str(m.content) for m in r.llm.invoke_calls[0]}
    added = "\n".join(str(m.content) for m in r.llm.invoke_calls[1] if str(m.content) not in first_contents)
    assert added, "the retry added no text to the planner's messages"
    for part in (NO_INVENTED_RULE, BEV, "gallons"):
        assert part in added, part
    # spec 022 AC-8: the invented 6 is in the added text as a whole number (the question's "60" does not count)
    assert re.search(r"(?<![\d.])6(?![\d])", added), added
    assert bev_calls(r) == [GOOD]


def test_ec14_first_call_does_not_carry_the_feedback(run, text_of):
    """Covers: AC-2 (wrong), EC-14. The first planner call has no feedback (the rule lives in the tool description)."""
    r = run(Q60, [[(BEV, BAD)], [(BEV, GOOD)]])
    assert NO_INVENTED_RULE not in text_of(r.llm.invoke_calls[0])


def test_ec14_outcome_fields(run):
    """Covers: AC-2 (right), EC-14. retried True; one RejectedCall with the first plan's args and invented values."""
    o = run(Q60, [[(BEV, BAD)], [(BEV, GOOD)]]).outcome
    assert o.retried is True
    assert len(o.rejected) == 1
    rc = o.rejected[0]
    assert isinstance(rc, RejectedCall)
    assert rc.name == BEV
    assert rc.args == BAD
    assert rc.invented == {"gallons": (6,)}
    assert o.first_plan.calls[0].args == BAD
    assert o.plan.calls[0].args == GOOD
    assert o.first_plan != o.plan


def test_ec14_tools_hold_the_args_that_ran(run):
    """Covers: AC-2 (right), EC-14. outcome.tools[0].args is what the runner got."""
    r = run(Q60, [[(BEV, BAD)], [(BEV, GOOD)]])
    assert [t.args for t in r.outcome.tools] == [GOOD]


def test_ec14_feedback_names_every_invented_value(run, text_of):
    """Covers: AC-2 (right), EC-14. Two rejected calls: each tool name, argument and value is in the feedback."""
    q = "How many cambros for peach tea, and how do I make lemonade"
    first = [(BEV, {"item": "cambros", "drinks": ["peach tea"], "gallons": [37, 38]}),
             (REC, {"recipe": "lemonade", "guests": 91})]
    r = run(q, [first, [(BEV, {"item": "cambros", "drinks": ["peach tea"]}), (REC, {"recipe": "lemonade"})]])
    second = text_of(r.llm.invoke_calls[1])
    for part in (BEV, REC, "gallons", "guests", "37", "38", "91"):
        assert part in second, part
    assert [rc.name for rc in r.outcome.rejected] == [BEV, REC]
    assert [rc.invented for rc in r.outcome.rejected] == [{"gallons": (37, 38)}, {"guests": (91,)}]


def test_only_calls_with_invented_numbers_are_rejected(run):
    """Covers: AC-2 (boundary), EC-14. A clean call in the same plan is not in rejected."""
    q = "How many cambros for 5 gallons of coffee, and how do I make lemonade for 75 guests"
    clean = (BEV, {"item": "cambros", "drinks": ["coffee"], "gallons": [5]})
    dirty = (REC, {"recipe": "lemonade", "guests": 75, "gallons": 3})
    r = run(q, [[clean, dirty], [clean, (REC, {"recipe": "lemonade", "guests": 75})]])
    assert [rc.name for rc in r.outcome.rejected] == [REC]


# ---------------------------------------------------------------- EC-15

def test_ec15_still_invents_so_gallons_dropped(run):
    """Covers: AC-2 (wrong), EC-15, EC-21. The runner gets the call without gallons; no third planner call."""
    r = run(Q60, [[(BEV, BAD)], [(BEV, BAD)]])
    assert len(r.llm.invoke_calls) == 2
    assert bev_calls(r) == [GOOD]
    assert r.outcome.retried is True
    assert [t.args for t in r.outcome.tools] == [GOOD]
    assert len(r.llm.stream_calls) <= 1


def test_ec15_other_args_unchanged(run):
    """Covers: AC-2 (boundary), EC-15. item, drinks and guests reach the runner exactly as planned."""
    args = bev_calls(run(Q60, [[(BEV, BAD)], [(BEV, BAD)]]))[0]
    assert args["item"] == "cambros"
    assert args["drinks"] == ["peach tea"]
    assert args["guests"] == 60
    assert "gallons" not in args


def test_ec15_whole_gallons_list_dropped_if_any_value_invented(run):
    """Covers: AC-2 (boundary), EC-15. One invented value in [7, 4] drops the whole gallons list."""
    q = "7 gallons of peach tea and 3 gallons of hot water"
    bad = {"item": "cambros", "drinks": ["peach tea", "hot water"], "gallons": [7, 4]}
    r = run(q, [[(BEV, bad)], [(BEV, bad)]])
    assert bev_calls(r) == [{"item": "cambros", "drinks": ["peach tea", "hot water"]}]


# ---------------------------------------------------------------- EC-16

def test_ec16_drop_keeps_real_guests(run):
    """Covers: AC-2 (right), EC-16. Real guests 60 stays; invented gallons goes."""
    r = run(Q60, [[(BEV, BAD)], [(BEV, BAD)]])
    assert bev_calls(r)[0]["guests"] == 60
    assert "gallons" not in bev_calls(r)[0]


def test_ec16_drop_only_invented_guests_keeps_real_gallons(run):
    """Covers: AC-2 (right), EC-16. Invented guests goes; real gallons [6] stays."""
    q = "How many cambros for 6 gallons of peach tea"
    bad = {"item": "cambros", "drinks": ["peach tea"], "gallons": [6], "guests": 60}
    r = run(q, [[(BEV, bad)], [(BEV, bad)]])
    assert bev_calls(r) == [{"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}]


def test_ec16_second_plan_dropping_only_matters_for_the_second_plan(run):
    """Covers: AC-2 (boundary), EC-16. If the retry plan is clean, nothing of it is dropped."""
    q = "How many cambros for 6 gallons of peach tea"
    r = run(q, [[(BEV, {"item": "cambros", "drinks": ["peach tea"], "gallons": [6], "guests": 60})],
                [(BEV, {"item": "cambros", "drinks": ["peach tea"], "gallons": [6]})]])
    assert bev_calls(r) == [{"item": "cambros", "drinks": ["peach tea"], "gallons": [6]}]


def test_retry_plan_with_a_new_invented_number_is_dropped(run):
    """Covers: AC-2 (wrong), EC-15, EC-16. The second plan is checked too: a new invented value is dropped."""
    r = run(Q60, [[(BEV, BAD)], [(BEV, {**GOOD, "gallons": [12]})]])
    assert bev_calls(r) == [GOOD]
    assert len(r.llm.invoke_calls) == 2


# ---------------------------------------------------------------- EC-17

def test_ec17_retry_changes_the_route(run, doc):
    """Covers: AC-2 (right), EC-17. First plan search + invented tool; second plan search only: route DOCS, no runner."""
    q = "Where are the lemons, and how many cambros for peach tea for 60 guests"
    search = (SEARCH, {"query": "where are the lemons"})
    docs = {"where are the lemons": [doc("Lemons are in the cooler.", "data/supplies/lemon.md")]}
    r = run(q, [[search, (BEV, BAD)], [search]], docs=docs)
    o = r.outcome
    assert o.plan.route == "DOCS"
    assert o.first_plan.route == "BOTH"
    assert o.retried is True
    assert len(o.rejected) == 1
    assert o.tools == ()
    assert bev_calls(r) == []
    assert r.runners[REC].calls == []
    assert [s.query for s in o.searches] == ["where are the lemons"]


# ---------------------------------------------------------------- EC-18

def test_ec18_recipe_retry_then_drop(run):
    """Covers: AC-2 (wrong), EC-18. A scale_recipe call with invented gallons: retried, then gallons dropped."""
    q = "How do I make lemonade for 75 guests?"
    bad = {"recipe": "lemonade", "guests": 75, "gallons": 3}
    r = run(q, [[(REC, bad)], [(REC, bad)]])
    assert len(r.llm.invoke_calls) == 2
    assert r.runners[REC].calls == [{"recipe": "lemonade", "guests": 75}]
    assert r.outcome.retried is True
    assert r.outcome.rejected[0].name == REC
    assert r.outcome.rejected[0].invented == {"gallons": (3,)}


def test_ec18_recipe_retry_fixes_it(run):
    """Covers: AC-2 (right), EC-18. The retry plan is clean: its args run unchanged."""
    q = "How do I make lemonade for 75 guests?"
    r = run(q, [[(REC, {"recipe": "lemonade", "guests": 75, "gallons": 3})],
                [(REC, {"recipe": "lemonade", "guests": 75})]])
    assert r.runners[REC].calls == [{"recipe": "lemonade", "guests": 75}]


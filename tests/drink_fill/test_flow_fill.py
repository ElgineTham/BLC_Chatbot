"""Spec 022, AC-4 (flow): EC-22 to EC-26, plus the interface changes of §3.2.

Unit tests of run_planned_turn with scripted fake planner and answer models, a fake store, fake runners and
the Appendix A catalog.
"""
from __future__ import annotations

import dataclasses
import inspect

from blc.flow import FilledDrinks, TurnOutcome, build_flow_graph, run_planned_turn

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
Q = "How many cups to bring for decaf, 40 guests"
CUPS40 = {"item": "cups", "guests": 40}
FILLED = {"item": "cups", "guests": 40, "drinks": ["Decaf"]}


def test_signatures_have_drink_catalog_last_defaulting_to_none():
    """Covers: AC-4 (right), §3.2. Both run_planned_turn and build_flow_graph take drink_catalog last, default None."""
    for fn in (run_planned_turn, build_flow_graph):
        params = list(inspect.signature(fn).parameters.values())
        assert params[-1].name == "drink_catalog"
        assert params[-1].default is None


def test_turn_outcome_gains_filled_as_its_last_field():
    """Covers: AC-4 (right), §3.2. TurnOutcome's last field is 'filled'."""
    assert dataclasses.fields(TurnOutcome)[-1].name == "filled"


def test_ec22_runner_gets_filled_args(run_fill):
    """Covers: AC-4 (right), EC-22. The bev runner gets the call with drinks; outcome.filled records it."""
    r = run_fill(Q, [[(BEV, dict(CUPS40))]])
    assert r.runners[BEV].calls == [FILLED]
    assert r.outcome.filled == FilledDrinks(0, ("Decaf",), "question")


def test_ec22_plan_tools_and_first_plan(run_fill):
    """Covers: AC-4 (right), EC-22. plan and tools show the drinks; first_plan (the planner's own output) does not."""
    o = run_fill(Q, [[(BEV, dict(CUPS40))]]).outcome
    assert o.plan.calls[0].args == FILLED
    assert o.first_plan.calls[0].args == CUPS40
    assert o.tools[0].args == FILLED
    assert o.rejected == ()


def test_ec22_fill_from_history_in_the_flow(run_fill):
    """Covers: AC-4 (right), EC-17, EC-22. Question '50' with a Decaf user turn in the history fills from history."""
    h = [{"role": "user", "content": "How many cups to bring for 2 gallons of decaf"},
         {"role": "assistant", "content": "How many guests?"}]
    r = run_fill("50", [[(BEV, {"item": "cups", "guests": 50})]], history=h)
    assert r.runners[BEV].calls == [{"item": "cups", "guests": 50, "drinks": ["Decaf"]}]
    assert r.outcome.filled == FilledDrinks(0, ("Decaf",), "history")


def test_ec22_both_route_fill_index(run_fill):
    """Covers: AC-4 (right), EC-16, EC-22. In a BOTH plan the bev call index is recorded and the search still runs."""
    q = "Do we bring lemons for hot water, and how many cups for hot water for 35 guests?"
    r = run_fill(q, [[(SEARCH, {"query": "lemons for hot water"}), (BEV, {"item": "cups", "guests": 35})]])
    assert r.outcome.filled == FilledDrinks(1, ("Hot water",), "question")
    assert r.runners[BEV].calls == [{"item": "cups", "guests": 35, "drinks": ["Hot water"]}]
    assert [s.query for s in r.outcome.searches] == ["lemons for hot water"]


def test_ec23_no_catalog_means_no_fill(run_fill):
    """Covers: AC-4 (wrong), EC-23. Without drink_catalog the runner gets the call as planned; filled is None."""
    r = run_fill(Q, [[(BEV, dict(CUPS40))]], with_catalog=False)
    assert r.runners[BEV].calls == [CUPS40]
    assert r.outcome.filled is None
    assert r.outcome.plan.calls[0].args == CUPS40


def test_ec23_explicit_none_means_no_fill(run_fill):
    """Covers: AC-4 (wrong), EC-23. drink_catalog=None turns the fill off."""
    r = run_fill(Q, [[(BEV, dict(CUPS40))]], catalog_value=None)
    assert r.runners[BEV].calls == [CUPS40]
    assert r.outcome.filled is None


def test_catalog_may_be_passed_positionally(run_fill):
    """Covers: AC-4 (right), §3.2. drink_catalog is the 8th positional argument (keyword or positional)."""
    r = run_fill(Q, [[(BEV, dict(CUPS40))]], positional=True)
    assert r.runners[BEV].calls == [FILLED]
    assert r.outcome.filled == FilledDrinks(0, ("Decaf",), "question")


def test_ec24_no_fill_needed(run_fill):
    """Covers: AC-4 (wrong), EC-24. A call that already has drinks: filled None, the runner gets it as planned."""
    args = {"item": "cups", "drinks": ["decaf"], "guests": 40}
    r = run_fill(Q, [[(BEV, dict(args))]])
    assert r.outcome.filled is None
    assert r.runners[BEV].calls == [args]
    assert r.outcome.plan == r.outcome.first_plan


def test_ec24_docs_only_turn(run_fill):
    """Covers: AC-4 (wrong), EC-24. A search-only turn about decaf: filled None, no tool runs, as in spec 021."""
    r = run_fill("Where is the decaf?", [[(SEARCH, {"query": "where is the decaf"})]])
    assert r.outcome.filled is None
    assert r.outcome.tools == ()
    assert r.runners[BEV].calls == [] and r.runners[REC].calls == []


def test_ec24_two_bev_calls_not_filled_in_the_flow(run_fill):
    """Covers: AC-4 (wrong), EC-14, EC-24. Two bev calls, one drink-less: the runner gets both as planned."""
    q = "How many cups and gallons of decaf do I need for 40 guests?"
    first = {"item": "cups", "guests": 40}
    second = {"item": "gallons", "drinks": ["decaf"], "guests": 40}
    r = run_fill(q, [[(BEV, dict(first)), (BEV, dict(second))]])
    assert r.outcome.filled is None
    assert r.runners[BEV].calls == [first, second]


def test_no_drink_named_anywhere_in_the_flow(run_fill):
    """Covers: AC-4 (wrong), EC-21, EC-24. A drink-less call with no drink in question or history stays as planned."""
    r = run_fill("How many cups for 45 guests?", [[(BEV, {"item": "cups", "guests": 45})]])
    assert r.outcome.filled is None
    assert r.runners[BEV].calls == [{"item": "cups", "guests": 45}]


def test_ec25_fill_after_the_retry(run_fill):
    """Covers: AC-4 (right), EC-25. First plan invents gallons [6]; the retry plan is clean and is then filled."""
    bad = {"item": "cups", "guests": 40, "gallons": [6]}
    r = run_fill(Q, [[(BEV, bad)], [(BEV, dict(CUPS40))]])
    o = r.outcome
    assert r.runners[BEV].calls == [FILLED]
    assert o.retried is True
    assert len(o.rejected) == 1
    assert o.rejected[0].args == bad
    assert o.filled == FilledDrinks(0, ("Decaf",), "question")
    assert o.first_plan.calls[0].args == bad
    assert o.plan.calls[0].args == FILLED


def test_ec25_fill_after_the_drop(run_fill):
    """Covers: AC-4 (right), EC-25. The retry still invents gallons: it is dropped and the drinks are filled on the result."""
    bad = {"item": "cups", "guests": 40, "gallons": [6]}
    r = run_fill(Q, [[(BEV, dict(bad))], [(BEV, dict(bad))]])
    assert r.runners[BEV].calls == [FILLED]
    assert r.outcome.retried is True
    assert r.outcome.filled == FilledDrinks(0, ("Decaf",), "question")


def test_ec26_same_number_of_model_calls_with_and_without_fill(run_fill):
    """Covers: AC-4 (boundary), EC-26, NFR-2. The fill adds no planner or answer call."""
    on = run_fill(Q, [[(BEV, dict(CUPS40))]])
    off = run_fill(Q, [[(BEV, dict(CUPS40))]], with_catalog=False)
    assert len(on.llm.invoke_calls) == len(off.llm.invoke_calls) == 1
    assert len(on.llm.stream_calls) == len(off.llm.stream_calls)


def test_ec26_same_model_calls_with_retry(run_fill):
    """Covers: AC-4 (boundary), EC-26. With a retry the counts are still equal with the fill on and off."""
    bad = {"item": "cups", "guests": 40, "gallons": [6]}
    on = run_fill(Q, [[(BEV, dict(bad))], [(BEV, dict(CUPS40))]])
    off = run_fill(Q, [[(BEV, dict(bad))], [(BEV, dict(CUPS40))]], with_catalog=False)
    assert len(on.llm.invoke_calls) == len(off.llm.invoke_calls) == 2
    assert len(on.llm.stream_calls) == len(off.llm.stream_calls)


def test_fill_does_not_change_the_reply_path_inputs_other_than_tool_args(run_fill):
    """Covers: AC-4 (boundary), §4.3. The question, route and fallback of the outcome are unaffected by the fill."""
    on = run_fill(Q, [[(BEV, dict(CUPS40))]]).outcome
    off = run_fill(Q, [[(BEV, dict(CUPS40))]], with_catalog=False).outcome
    assert on.question == off.question
    assert on.plan.route == off.plan.route and on.plan.fallback == off.plan.fallback
    assert on.history == off.history

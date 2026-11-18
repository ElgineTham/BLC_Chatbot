"""Spec 030 section 6.2 ARGS-7 (AC-14): the eval scorer of section 4.2 on hand-made plans. Unit, no model."""
from __future__ import annotations

import pytest

import food_wiring_helpers as fwh
from blc.planner import Plan, PlannedCall

FOOD = "calculate_food_item"
BEV = "calculate_bev_item"
SEARCH = "search_documents"


def tool_plan(*calls):
    return Plan("TOOL", tuple(PlannedCall(n, a) for n, a in calls), False)


def docs_plan(*queries, tools=()):
    calls = [PlannedCall(SEARCH, {"query": q}) for q in queries] + [PlannedCall(n, a) for n, a in tools]
    return Plan("BOTH" if tools else "DOCS", tuple(calls), False)


def score(case_id, plan):
    return fwh.score_case(fwh.CASES[case_id], plan)


# ---------------------------------------------------------------- tools: passes

@pytest.mark.parametrize("item", ["Fork", "forks", "fork", " FORKS ", "Forks"])
def test_item_singular_and_case_pass(item):
    """Covers: AC-14 (right), ARGS-7. 'Fork' equals forks (singular, casefold, strip)."""
    assert score("ARGS-3", tool_plan((FOOD, {"item": "knives", "guests": 60}),
                                     (FOOD, {"item": item, "guests": 60}))) == set()


@pytest.mark.parametrize("item", ["small_plate", "small-plates", "Small  Plates", "small plate"])
def test_item_underscore_hyphen_and_spaces_pass(item):
    """Covers: AC-14 (right), ARGS-7. small_plate / small-plates / extra spaces equal 'small plates'."""
    assert score("ARGS-6", tool_plan((FOOD, {"item": item, "guests": 50}))) == set()


def test_knife_equals_knives():
    """Covers: AC-14 (right), ARGS-7. The singular 'knife' equals knives."""
    assert score("FT-1", tool_plan((FOOD, {"item": "knife", "guests": 70}))) == set()


def test_napkin_call_with_wrong_guests_still_passes():
    """Covers: AC-14 (right), ARGS-7. A napkin call: guests is not compared."""
    plan = tool_plan((FOOD, {"item": "dinner napkins", "meal": "lunch", "guests": 999}))
    assert score("ARGS-4", plan) == set()


def test_count_call_with_wrong_meal_still_passes():
    """Covers: AC-14 (right), ARGS-7. A count call: meal is not compared."""
    plan = tool_plan((FOOD, {"item": "spoons", "guests": 45, "meal": "dinner"}))
    assert score("ARGS-1", plan) == set()


@pytest.mark.parametrize("guests", [45, 45.0, "45", " 45 "])
def test_guests_equal_by_value(guests):
    """Covers: AC-14 (boundary), ARGS-7. 45, 45.0 and a numeric string are the same number."""
    assert score("ARGS-1", tool_plan((FOOD, {"item": "spoons", "guests": guests}))) == set()


@pytest.mark.parametrize("meal", ["Lunch", " lunch ", "LUNCH"])
def test_meal_strip_and_casefold(meal):
    """Covers: AC-14 (boundary), ARGS-7. meal is equal after strip and casefold."""
    assert score("ARGS-4", tool_plan((FOOD, {"item": "dinner napkins", "meal": meal}))) == set()


def test_order_of_calls_does_not_matter():
    """Covers: AC-14 (boundary), ARGS-7. Expected calls match as a multiset."""
    plan = tool_plan((FOOD, {"item": "forks", "guests": 60}), (FOOD, {"item": "knives", "guests": 60}))
    assert score("ARGS-3", plan) == set()


def test_names_only_ignores_arguments():
    """Covers: AC-14 (right), ARGS-7. CALL-1 compares names only: any food call passes."""
    assert score("CALL-1", tool_plan((FOOD, {}))) == set()
    assert score("CALL-1", tool_plan((FOOD, {"item": "spoons", "guests": 5}))) == set()


# ---------------------------------------------------------------- tools: failures

def test_wrong_guests_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. guests 46 for an expected 45 fails 'tools' only."""
    assert score("ARGS-1", tool_plan((FOOD, {"item": "spoons", "guests": 46}))) == {"tools"}


def test_missing_guests_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. A count call with no guests fails 'tools'."""
    assert score("ARGS-1", tool_plan((FOOD, {"item": "spoons"}))) == {"tools"}


def test_missing_meal_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. A napkin call with no meal fails 'tools'."""
    assert score("ARGS-4", tool_plan((FOOD, {"item": "dinner napkins"}))) == {"tools"}


def test_wrong_meal_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. A napkin call with another meal fails 'tools'."""
    assert score("ARGS-4", tool_plan((FOOD, {"item": "dinner napkins", "meal": "breakfast"}))) == {"tools"}


def test_wrong_item_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. forks for an expected spoons fails 'tools'."""
    assert score("ARGS-1", tool_plan((FOOD, {"item": "forks", "guests": 45}))) == {"tools"}


def test_extra_tool_call_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. An extra tool call fails 'tools'."""
    plan = tool_plan((FOOD, {"item": "spoons", "guests": 45}), (FOOD, {"item": "forks", "guests": 45}))
    assert score("ARGS-1", plan) == {"tools"}


def test_missing_call_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. Only one of two expected calls fails 'tools'."""
    assert score("ARGS-3", tool_plan((FOOD, {"item": "forks", "guests": 60}))) == {"tools"}


def test_duplicate_call_cannot_match_two_expected():
    """Covers: AC-14 (wrong), ARGS-7. Each expected call matches exactly one actual call: forks twice does
    not stand in for knives and forks."""
    plan = tool_plan((FOOD, {"item": "forks", "guests": 60}), (FOOD, {"item": "forks", "guests": 60}))
    assert score("ARGS-3", plan) == {"tools"}


@pytest.mark.parametrize("guests", [True, False, None, "many", [60], {"n": 60}])
def test_non_numbers_fail(guests):
    """Covers: AC-14 (wrong), ARGS-7. A boolean (never a number), None, text or a container is not 60."""
    plan = tool_plan((FOOD, {"item": "forks", "guests": guests}), (FOOD, {"item": "knives", "guests": 60}))
    assert score("ARGS-3", plan) == {"tools"}


def test_boolean_true_is_not_one():
    """Covers: AC-14 (boundary), ARGS-7. True is not the number 1, even for an expected 1."""
    case = {"id": "X", "area": "ARGS", "route": "TOOL", "question": "q", "history": None,
            "tools": [fwh.cnt("forks", 1)], "keep": []}
    assert fwh.score_case(case, tool_plan((FOOD, {"item": "forks", "guests": True}))) == {"tools"}
    assert fwh.score_case(case, tool_plan((FOOD, {"item": "forks", "guests": 1}))) == set()


def test_non_dict_args_fail_without_raising():
    """Covers: AC-14 (wrong), ARGS-7. Arguments that are not a dict fail the case; the scorer does not raise."""
    plan = Plan("TOOL", (PlannedCall(FOOD, None),), False)
    assert score("ARGS-1", plan) == {"tools"}


def test_wrong_tool_name_fails_tools():
    """Covers: AC-14 (wrong), CALL-5. CALL-5 expects the bev tool: a food call fails 'tools'."""
    assert score("CALL-5", tool_plan((FOOD, {"item": "forks", "guests": 70}))) == {"tools"}
    assert score("CALL-5", tool_plan((BEV, {"item": "cups", "guests": 70}))) == set()


def test_bev_plus_food_call_fails_call_5():
    """Covers: AC-14 (wrong), CALL-5. 'no calculate_food_item': an extra food call next to the bev call fails."""
    plan = tool_plan((BEV, {"item": "cups", "guests": 70}), (FOOD, {"item": "forks", "guests": 70}))
    assert score("CALL-5", plan) == {"tools"}


# ---------------------------------------------------------------- route and search

def test_wrong_route_fails_route():
    """Covers: AC-14 (wrong), ARGS-7. A DOCS plan for a TOOL case fails 'route' (and 'tools' and 'search')."""
    failed = score("CALL-1", docs_plan("forks"))
    assert "route" in failed


def test_search_in_a_tool_case_fails_search():
    """Covers: AC-14 (wrong), ARGS-7. A TOOL case with a search call fails 'search' (route BOTH too)."""
    plan = docs_plan("forks", tools=[(FOOD, {"item": "forks", "guests": 90})])
    failed = score("CALL-1", plan)
    assert "search" in failed and "route" in failed and "tools" not in failed


def test_docs_case_with_no_search_fails_search():
    """Covers: AC-14 (wrong), ARGS-7. A DOCS case needs at least one search call."""
    assert "search" in score("FD-1", tool_plan((FOOD, {"item": "forks", "guests": 70})))


def test_docs_case_keep_groups_pass():
    """Covers: AC-14 (right), ARGS-7. FD-1: the query has 'croissant' and a LOC term; no tool call."""
    assert score("FD-1", docs_plan("Where are the croissants kept?")) == set()


def test_docs_case_queries_are_joined():
    """Covers: AC-14 (boundary), ARGS-7. Keep groups may be met by different queries (joined, casefolded)."""
    assert score("FD-1", docs_plan("CROISSANT", "where")) == set()


def test_docs_case_missing_keep_term_fails_search():
    """Covers: AC-14 (wrong), ARGS-7. FD-1 with a query that never names the croissants fails 'search'."""
    assert score("FD-1", docs_plan("where is the stuff kept")) == {"search"}


def test_docs_case_missing_location_term_fails_search():
    """Covers: AC-14 (wrong), ARGS-7. FD-1 needs a LOC term as well as the subject."""
    assert score("FD-1", docs_plan("croissant")) == {"search"}


def test_either_term_of_a_group_is_enough():
    """Covers: AC-14 (boundary), ARGS-7. FD-5 keeps 'bagel' or 'cream cheese'."""
    assert score("FD-5", docs_plan("bagel toppings")) == set()
    assert score("FD-5", docs_plan("cream cheese for bagels")) == set()
    assert score("FD-5", docs_plan("what comes with them")) == {"search"}


def test_docs_case_with_a_tool_call_fails_tools():
    """Covers: AC-14 (wrong), ARGS-7. A DOCS case expects zero tool calls: a food call fails 'tools'."""
    plan = docs_plan("where are the croissants kept", tools=[(FOOD, {"item": "forks", "guests": 70})])
    failed = score("FD-1", plan)
    assert "tools" in failed and "route" in failed


def test_call_6_docs_case_with_a_search_and_no_tool_passes():
    """Covers: AC-14 (right), CALL-6. CALL-6 needs only a search and no tool call."""
    assert score("CALL-6", docs_plan("napkins for iced tea")) == set()
    assert "tools" in score("CALL-6", docs_plan("napkins", tools=[(FOOD, {"item": "dinner napkins"})]))


def test_scorer_is_pure():
    """Covers: AC-14 (boundary), ARGS-7. Scoring twice gives the same answer and does not change the plan."""
    plan = tool_plan((FOOD, {"item": "spoons", "guests": 45}))
    before = (plan.route, plan.calls)
    assert score("ARGS-1", plan) == score("ARGS-1", plan) == set()
    assert (plan.route, plan.calls) == before

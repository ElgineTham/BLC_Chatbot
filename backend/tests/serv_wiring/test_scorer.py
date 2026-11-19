"""Spec 043 section 4.4 (AC-10 to AC-12 scoring). Unit: the pure scorer on hand-made plans.

The scorer is a test-side helper (serv_wiring_helpers.score_case). Totals are judged by running the serving
call's arguments through run_serv_tool; here with the Appendix A rules so no real data file is read.
"""
from __future__ import annotations

import pytest

import serv_wiring_helpers as swh
from blc.planner import Plan, PlannedCall
from blc.tools.serv_tools import run_serv_tool

SERV, FOOD, SEARCH = swh.SERV, swh.FOOD, swh.SEARCH


@pytest.fixture
def run_tool(rules):
    return lambda args: run_serv_tool(args, rules=rules)


def _case(**kw):
    base = {"id": "X-1", "area": "ARGS", "route": "TOOL", "question": "q", "history": None,
            "tools": [SERV], "totals": {"small tongs": 4}, "keyword": None}
    base.update(kw)
    return base


def _plan(*calls, route="TOOL"):
    return Plan(route, tuple(PlannedCall(n, a) for n, a in calls), False)


def _follow_3_appendix_a():
    """FOLLOW-3 with its expected totals taken from spec 042 Appendix A (spec 043 section 6, revision 4), not the
    real-rule totals of the eval table: 30 classic deli sandwiches give large tongs 1 and mayo/mustard 2."""
    case = dict(swh.CASES["FOLLOW-3"])
    case["totals"] = {"large tongs": 1, "mayo/mustard": 2}
    return case


CROISSANTS_3_DOZEN ={"items": [{"food": "butter croissants", "qty": 3}]}


def test_matching_plan_passes(run_tool):
    """Covers: AC-11 (right), 4.4. Route, tool names and totals all match: no failed check."""
    assert swh.score_case(_case(), _plan((SERV, CROISSANTS_3_DOZEN)), run_tool) == set()


def test_alias_and_unit_spelling_pass_by_totals(run_tool):
    """Covers: AC-11 (right), 4.4. A food alias and the unit spelled 'dz' that give the same totals pass."""
    args = {"items": [{"food": "Butter croissants served with raspberry preserves", "qty": 3, "unit": "dz"}]}
    assert swh.score_case(_case(), _plan((SERV, args)), run_tool) == set()


def test_wrong_totals_fail_even_with_right_tool(run_tool):
    """Covers: AC-11 (wrong), 4.4. 3 dozen read as 3 each gives other totals: only 'totals' fails."""
    args = {"items": [{"food": "butter croissants", "qty": 3, "unit": "each"}]}
    assert swh.score_case(_case(), _plan((SERV, args)), run_tool) == {"totals"}


def test_package_line_read_as_dozens_fails(run_tool):
    """Covers: AC-11 (wrong), 4.4. 70 croissants sent without unit each (read as 70 dozen) fail the totals;
    with unit each (6 small tongs) they pass."""
    case = _case(totals={"small tongs": 6})
    as_dozen = {"items": [{"food": "butter croissants", "qty": 70}]}
    as_each = {"items": [{"food": "butter croissants", "qty": 70, "unit": "each"}]}
    assert swh.score_case(case, _plan((SERV, as_dozen)), run_tool) == {"totals"}
    assert swh.score_case(case, _plan((SERV, as_each)), run_tool) == set()


def test_need_info_or_invalid_result_fails_totals(run_tool):
    """Covers: AC-11 (wrong), 4.4. A call whose result is not 'ok' fails the totals check."""
    no_qty = {"items": [{"food": "butter croissants"}]}
    bad_food = {"items": [{"food": "lasagna", "qty": 3}]}
    assert swh.score_case(_case(), _plan((SERV, no_qty)), run_tool) == {"totals"}
    assert swh.score_case(_case(), _plan((SERV, bad_food)), run_tool) == {"totals"}


def test_follow_3_totals_or_ask_accepts_ok_totals_or_need_info(run_tool):
    """Covers: AC-12 (right), 4.4 check 5 (revision 4). FOLLOW-3: right totals pass; a need_info result passes."""
    case = _follow_3_appendix_a()
    deli_30 = {"items": [{"food": "classic deli sandwiches", "qty": 30, "unit": "each"}]}
    no_qty = {"items": [{"food": "classic deli sandwiches"}]}
    assert swh.score_case(case, _plan((SERV, deli_30)), run_tool) == set()
    assert swh.score_case(case, _plan((SERV, no_qty)), run_tool) == set()


def test_follow_3_wrong_totals_or_invalid_fail(run_tool):
    """Covers: AC-12 (wrong), 4.4 check 5 (revision 4). Wrong totals (ok but other numbers) and an invalid
    result fail 'totals'; so does a plan with no serving call (search only)."""
    case = _follow_3_appendix_a()
    wrong = {"items": [{"food": "classic deli sandwiches", "qty": 100, "unit": "each"}]}  # Appendix A: mayo 4
    invalid = {"items": [{"food": "lasagna", "qty": 30}]}
    assert swh.score_case(case, _plan((SERV, wrong)), run_tool) == {"totals"}
    assert swh.score_case(case, _plan((SERV, invalid)), run_tool) == {"totals"}
    search_only = _plan((SEARCH, {"query": "deli sandwiches utensils"}), route="DOCS")
    assert {"route", "tools", "totals"} <= swh.score_case(case, search_only, run_tool)


def test_need_info_passes_only_for_follow_3(run_tool):
    """Covers: AC-11 (wrong), 4.4 (boundary). Other cases with totals still fail on need_info (no ask_ok)."""
    assert swh.CASES["FOLLOW-3"]["ask_ok"] is True
    assert not any(c["ask_ok"] for cid, c in swh.CASES.items() if cid != "FOLLOW-3")


def test_non_dict_args_fail_totals_without_raising(run_tool):
    """Covers: AC-11 (boundary), 4.4. Arguments that are not a dict fail 'totals' (no exception)."""
    assert swh.score_case(_case(), _plan((SERV, None)), run_tool) == {"totals"}


def test_wrong_route_fails_route(run_tool):
    """Covers: AC-10 (wrong), 4.4. A BOTH plan for a TOOL case fails 'route' (and 'tools' is judged apart)."""
    plan = _plan((SEARCH, {"query": "tongs"}), (SERV, CROISSANTS_3_DOZEN), route="BOTH")
    assert swh.score_case(_case(), plan, run_tool) == {"route"}


def test_search_calls_are_ignored_by_tool_names(run_tool):
    """Covers: AC-10 (boundary), 4.4. search_documents calls do not count as tool names."""
    case = _case(route="BOTH")
    plan = _plan((SEARCH, {"query": "x"}), (SERV, CROISSANTS_3_DOZEN), route="BOTH")
    assert swh.score_case(case, plan, run_tool) == set()


def test_wrong_tool_name_fails_tools(run_tool):
    """Covers: AC-10 (wrong), 4.4. CALL-3 shape: the food tool is expected; a serving call fails 'tools'."""
    case = _case(tools=[FOOD], totals=None)
    assert swh.score_case(case, _plan((SERV, CROISSANTS_3_DOZEN)), run_tool) == {"tools"}
    assert swh.score_case(case, _plan((FOOD, {"item": "forks", "guests": 60})), run_tool) == set()


def test_extra_tool_call_fails_tools(run_tool):
    """Covers: AC-10 (boundary), 4.4. Names are compared as a multiset: an extra call fails 'tools'."""
    case = _case(totals=None)
    plan = _plan((SERV, CROISSANTS_3_DOZEN), (FOOD, {"item": "forks", "guests": 60}))
    assert swh.score_case(case, plan, run_tool) == {"tools"}
    plan = _plan((SERV, CROISSANTS_3_DOZEN), (SERV, CROISSANTS_3_DOZEN))
    assert swh.score_case(case, plan, run_tool) == {"tools"}


def test_docs_case_needs_a_search_with_the_keyword(run_tool):
    """Covers: AC-10 (right), AC-12 (right), 4.4. CALL-4 / FOLLOW-4 shape: DOCS, no tool, a search whose query
    contains the keyword (casefolded)."""
    case = _case(route="DOCS", tools=[], totals=None, keyword="scone")
    assert swh.score_case(case, _plan((SEARCH, {"query": "Where are the SCONES kept"}), route="DOCS"),
                          run_tool) == set()


def test_docs_case_without_the_keyword_fails_search(run_tool):
    """Covers: AC-10 (wrong), AC-12 (wrong), 4.4. A search whose query lacks the keyword fails 'search'."""
    case = _case(route="DOCS", tools=[], totals=None, keyword="muffin")
    plan = _plan((SEARCH, {"query": "where is the bakery rack"}), route="DOCS")
    assert swh.score_case(case, plan, run_tool) == {"search"}


def test_docs_case_with_a_tool_call_fails_tools(run_tool):
    """Covers: AC-12 (wrong), 4.4. FOLLOW-4: a serving call where only a search is expected fails 'tools' and
    'route' (BOTH)."""
    case = _case(route="DOCS", tools=[], totals=None, keyword="muffin")
    plan = _plan((SEARCH, {"query": "muffin"}), (SERV, CROISSANTS_3_DOZEN), route="BOTH")
    assert swh.score_case(case, plan, run_tool) == {"route", "tools"}


def test_search_check_is_skipped_for_tool_cases(run_tool):
    """Covers: 4.4 (boundary). A case with no keyword does not check searches."""
    assert swh.score_case(_case(), _plan((SERV, CROISSANTS_3_DOZEN)), run_tool) == set()


def test_case_table_has_four_cases_per_area():
    """Covers: 4.4 (boundary). The case table has 4 CALL, 4 ARGS and 4 FOLLOW cases; the threshold is 3."""
    from collections import Counter

    assert Counter(c["area"] for c in swh.CASES.values()) == {"CALL": 4, "ARGS": 4, "FOLLOW": 4}
    assert swh.THRESHOLD == 3

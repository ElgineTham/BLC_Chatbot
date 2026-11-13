"""Spec 016 AC-3: the eval's scorer (section 4.2) on hand-made traces (EC-13, NFR-6). Unit; no model.

The scorer comes from conftest.py (fixture `score_case`). The calculators run on the Appendix A catalog and the
spec 015 test book from tmp_path, so nothing under data/ is read (NFR-2).
"""

from __future__ import annotations

import pytest

from blc.router import RouteDecision, RoutedPart
from blc.tools.bev_tools import run_bev_tool
from blc.tools.recipe_tools import run_recipe_tool
from blc.trace import ToolCallLog, ToolStage, TurnTrace

BEV = "calculate_bev_item"
RECIPE = "scale_recipe"
TXT = "result text"


def by_id(cases, cid):
    return next(c for c in cases if c["id"] == cid)


def call(name, args, result=TXT, refused=False):
    return ToolCallLog(name, args, result, refused)


def stage(part, *calls, tool_text=TXT):
    return ToolStage(part, tuple(calls), tool_text, False)


def trace(parts, stages, question="q"):
    kind = "TOOL" if all(p.route == "TOOL" for p in parts) else "BOTH" if any(p.route == "TOOL" for p in parts) else "DOCS"
    return TurnTrace(question, (), None, RouteDecision(tuple(parts), kind, False), tuple(stages), None)


@pytest.fixture
def score(score_case, catalog, book):
    """score(trace, case) -> Score, with the calculators on the test data."""
    def _score(t, case):
        return score_case(t, case, lambda a: run_bev_tool(a, catalog), lambda a: run_recipe_tool(a, book))
    return _score


def recipe_trace(args, tool=RECIPE, refused=False, result=TXT, text="How much lemon concentrate for 3 gallons of lemonade?"):
    return trace([RoutedPart("TOOL", text, tool)], [stage(text, call(RECIPE, args, result, refused))])


R3 = {"recipe": "lemonade", "gallons": 3}


# ---------------------------------------------------------------- EC-13 the listed traces (recipe case R1)

def test_matching_trace_passes(score, r_cases):
    """Covers: AC-3 (right), EC-13. A trace whose TOOL part, call and arguments match the case passes."""
    s = score(recipe_trace(R3), by_id(r_cases, "R1"))
    assert s.passed is True and s.stage != "corrected"
    assert s.first_call is True


def test_other_tool_fails_at_the_router(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. A TOOL part with the other tool fails with stage router."""
    s = score(recipe_trace(R3, tool=BEV), by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "router"


def test_tool_part_without_a_tool_fails_at_the_router(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. Extra: a TOOL part with tool None is not scale_recipe: stage router."""
    s = score(recipe_trace(R3, tool=None), by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "router"


def test_no_tool_part_fails_at_the_router(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. A route with only a DOCS part fails with stage router."""
    t = trace([RoutedPart("DOCS", "q", None)], [])
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "router"


def test_route_none_fails_at_the_router(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. Extra: a trace whose route is None fails with stage router."""
    t = TurnTrace("q", (), None, None, (), None)
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "router"


def test_two_tool_parts_for_a_one_call_case_fail_at_the_router(score, r_cases):
    """Covers: AC-3 (boundary), EC-13. Rule 1 wants one TOOL part per expected call: two parts for a one-call case is stage router."""
    parts = [RoutedPart("TOOL", "a", RECIPE), RoutedPart("TOOL", "b", RECIPE)]
    st = [stage("a", call(RECIPE, R3)), stage("b", call(RECIPE, R3))]
    s = score(trace(parts, st), by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "router"


def test_stage_without_calls_fails_with_no_call(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. A matching route whose stage has no calls fails with stage 'no call'."""
    t = trace([RoutedPart("TOOL", "q", RECIPE)], [ToolStage("q", (), None, False)])
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "no call"


def test_call_to_another_tool_fails_with_no_call(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. Rule 2: every call must be to the part's tool; a call to the other tool is stage 'no call'."""
    t = trace([RoutedPart("TOOL", "q", RECIPE)], [stage("q", call(BEV, {"item": "cambros"}, "error: unknown tool calculate_bev_item"))])
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "no call"


def test_wrong_gallons_fail_with_arguments(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. The accepted call gives 4 gallons where the case wants 3: stage arguments."""
    s = score(recipe_trace({"recipe": "lemonade", "gallons": 4}), by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "arguments"


def test_refused_first_call_then_right_call_is_corrected(score, r_cases):
    """Covers: AC-3 (right), EC-13. A refused first call and a right second call passes as 'corrected'."""
    t = trace(
        [RoutedPart("TOOL", "q", RECIPE)],
        [stage("q", call(RECIPE, {"recipe": "lemonade", "gallons": 2}, "invalid (check): x", True), call(RECIPE, R3))],
    )
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is True and s.stage == "corrected"
    assert s.first_call is False


def test_invalid_first_result_then_right_call_is_corrected(score, r_cases):
    """Covers: AC-3 (right), EC-13. A first call whose result starts with 'invalid' (not refused) and a right second call passes as 'corrected'."""
    t = trace(
        [RoutedPart("TOOL", "q", RECIPE)],
        [stage("q", call(RECIPE, {"recipe": "lemonade", "gallons": -1}, "invalid: gallons must be above 0"), call(RECIPE, R3))],
    )
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is True and s.stage == "corrected"


def test_only_call_refused_fails_with_arguments(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. A stage whose only call was refused has no accepted call: stage arguments."""
    s = score(recipe_trace(R3, refused=True, result="invalid (check): x"), by_id(r_cases, "R1"))
    assert s.passed is False and s.stage == "arguments"


def test_accepted_call_is_the_last_good_one(score, r_cases):
    """Covers: AC-3 (right), EC-13. A good call followed by a refused call: the accepted call is the good one, so the case passes and is not 'corrected'."""
    t = trace(
        [RoutedPart("TOOL", "q", RECIPE)],
        [stage("q", call(RECIPE, R3), call(RECIPE, {"recipe": "lemonade", "gallons": 9}, "invalid (check): x", True))],
    )
    s = score(t, by_id(r_cases, "R1"))
    assert s.passed is True and s.stage != "corrected"


# ---------------------------------------------------------------- recipe expectations

def test_from_guests_must_match(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. R4 wants gallons 2 from guests: gallons=2 plus guests=60 gives from_guests False and fails; guests=60 alone passes."""
    q = "How do I make lemonade for 60 guests?"
    bad = recipe_trace({"recipe": "lemonade", "gallons": 2, "guests": 60}, text=q)
    good = recipe_trace({"recipe": "lemonade", "guests": 60}, text=q)
    assert score(bad, by_id(r_cases, "R4")).stage == "arguments"
    assert score(good, by_id(r_cases, "R4")).passed is True


def test_guests_value_must_match_when_listed(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. R4 lists guests 60: guests 65 gives 3 gallons, so the case fails."""
    s = score(recipe_trace({"recipe": "lemonade", "guests": 65}), by_id(r_cases, "R4"))
    assert s.passed is False and s.stage == "arguments"


def test_user_gallons_win_in_r20(score, r_cases):
    """Covers: AC-3 (right, wrong), EC-13. R20 wants gallons 6 with from_guests False; guests may be passed or left out; guests alone (gives 6 gallons from guests) fails."""
    case = by_id(r_cases, "R20")
    assert score(recipe_trace({"recipe": "lemonade", "gallons": 6}), case).passed is True
    assert score(recipe_trace({"recipe": "lemonade", "gallons": 6, "guests": 140}), case).passed is True
    assert score(recipe_trace({"recipe": "lemonade", "guests": 140}), case).stage == "arguments"


def test_no_recipe_case_checks_the_name_as_given(score, r_cases):
    """Covers: AC-3 (right, wrong), EC-13. R15 expects status no_recipe and the name 'iced tea' (any case); an 'Iced Tea' call passes, a 'lemonade' call (status ok) fails."""
    case = by_id(r_cases, "R15")
    assert score(recipe_trace({"recipe": "Iced Tea", "gallons": 3}), case).passed is True
    assert score(recipe_trace({"recipe": "lemonade", "gallons": 3}), case).stage == "arguments"


def test_fractional_gallons_compare_exactly(score, r_cases):
    """Covers: AC-3 (boundary), EC-13. R6 wants 1.5 gallons: 1.5 passes, 1 fails."""
    case = by_id(r_cases, "R6")
    assert score(recipe_trace({"recipe": "lemonade", "gallons": 1.5}), case).passed is True
    assert score(recipe_trace({"recipe": "lemonade", "gallons": "1.5"}), case).passed is True
    assert score(recipe_trace({"recipe": "lemonade", "gallons": 1}), case).stage == "arguments"


# ---------------------------------------------------------------- two-call and DOCS-part cases

def test_docs_part_is_ignored(score, r_cases):
    """Covers: AC-3 (right), EC-13. R18 has one expected call: a DOCS part next to the TOOL part is ignored."""
    parts = [RoutedPart("DOCS", "Where are the concentrates kept", None), RoutedPart("TOOL", "how many ounces for 6 gallons?", RECIPE)]
    t = trace(parts, [stage("how many ounces for 6 gallons?", call(RECIPE, {"recipe": "lemonade", "gallons": 6}))])
    s = score(t, by_id(r_cases, "R18"))
    assert s.passed is True


def test_two_calls_in_order(score, r_cases):
    """Covers: AC-3 (right, wrong), EC-13. R19 wants scale_recipe then calculate_bev_item: right order passes; swapped parts fail at the router."""
    case = by_id(r_cases, "R19")
    rec_call = call(RECIPE, {"recipe": "lemonade", "gallons": 4})
    bev_call = call(BEV, {"item": "cambros", "drinks": ["lemonade"], "gallons": [4]})
    good = trace([RoutedPart("TOOL", "a", RECIPE), RoutedPart("TOOL", "b", BEV)], [stage("a", rec_call), stage("b", bev_call)])
    swapped = trace([RoutedPart("TOOL", "b", BEV), RoutedPart("TOOL", "a", RECIPE)], [stage("b", bev_call), stage("a", rec_call)])
    assert score(good, case).passed is True
    s = score(swapped, case)
    assert s.passed is False and s.stage == "router"


def test_second_part_wrong_arguments_fails(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. R19: a right first part and a second part with 5 gallons of lemonade fail with stage arguments."""
    case = by_id(r_cases, "R19")
    good = call(RECIPE, {"recipe": "lemonade", "gallons": 4})
    bad = call(BEV, {"item": "cambros", "drinks": ["lemonade"], "gallons": [5]})
    t = trace([RoutedPart("TOOL", "a", RECIPE), RoutedPart("TOOL", "b", BEV)], [stage("a", good), stage("b", bad)])
    s = score(t, case)
    assert s.passed is False and s.stage == "arguments"


def test_missing_second_stage_fails_with_no_call(score, r_cases):
    """Covers: AC-3 (wrong), EC-13. R19: two TOOL parts but only one tool stage: stage 'no call'."""
    case = by_id(r_cases, "R19")
    t = trace([RoutedPart("TOOL", "a", RECIPE), RoutedPart("TOOL", "b", BEV)],
              [stage("a", call(RECIPE, {"recipe": "lemonade", "gallons": 4}))])
    s = score(t, case)
    assert s.passed is False and s.stage == "no call"


# ---------------------------------------------------------------- beverage expectations

def bev_trace(args, text="q", **kw):
    return trace([RoutedPart("TOOL", text, BEV)], [stage(text, call(BEV, args, **kw))])


def test_beverage_case_passes_and_wrong_item_or_amount_fails(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13. B1 (cambros, Peach tea 8, no guests): the right call passes; item 'cups' or 8 changed to 6 fails with stage arguments."""
    case = by_id(b_cases, "B1")
    ok = {"item": "cambros", "drinks": ["peach tea"], "gallons": [8]}
    assert score(bev_trace(ok), case).passed is True
    assert score(bev_trace({**ok, "item": "cups"}), case).stage == "arguments"
    assert score(bev_trace({**ok, "gallons": [6]}), case).stage == "arguments"


def test_beverage_guests_given_where_none_expected_fails(score, b_cases):
    """Covers: AC-3 (wrong), EC-13. B1 says no guests: an extra guests=40 fails (stage arguments); guests null or 0 count as not given."""
    case = by_id(b_cases, "B1")
    ok = {"item": "cambros", "drinks": ["peach tea"], "gallons": [8]}
    assert score(bev_trace({**ok, "guests": 40}), case).stage == "arguments"
    assert score(bev_trace({**ok, "guests": None}), case).passed is True
    assert score(bev_trace({**ok, "guests": 0}), case).passed is True


def test_beverage_from_guests_case(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13. B5 (cambros, Brewed hot cider 2 from guests, guests 60): item, drinks and guests=60 pass; guests=100 (gives 4 gallons) fails with stage arguments."""
    case = by_id(b_cases, "B5")
    assert score(bev_trace({"item": "cambros", "drinks": ["brewed hot cider"], "guests": 60}), case).passed is True
    assert score(bev_trace({"item": "cambros", "drinks": ["brewed hot cider"], "guests": 100}), case).stage == "arguments"


def test_beverage_any_of_alternatives(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13. B7 accepts (Iced tea 4 from guests) or (no drinks), guests 110; Coffee instead of Iced tea fails."""
    case = by_id(b_cases, "B7")
    assert score(bev_trace({"item": "gallons", "drinks": ["iced tea"], "guests": 110}), case).passed is True
    assert score(bev_trace({"item": "gallons", "guests": 110}), case).passed is True
    assert score(bev_trace({"item": "gallons", "drinks": ["coffee"], "guests": 110}), case).stage == "arguments"


def test_beverage_hot_only_alternative(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13. B10 accepts no drinks or only hot drinks (guests 90); a cold drink fails."""
    case = by_id(b_cases, "B10")
    assert score(bev_trace({"item": "cups", "guests": 90}), case).passed is True
    assert score(bev_trace({"item": "cups", "drinks": ["coffee", "decaf"], "guests": 90}), case).passed is True
    assert score(bev_trace({"item": "cups", "drinks": ["iced tea"], "guests": 90}), case).stage == "arguments"


def test_beverage_not_on_menu_and_need_info_cases(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13. B18 wants status not_on_menu naming 'hot chocolate'; B19 wants need_info for Coffee with no gallons and no guests; a fully specified call fails B19."""
    b18, b19 = by_id(b_cases, "B18"), by_id(b_cases, "B19")
    assert score(bev_trace({"item": "cambros", "drinks": ["hot chocolate"], "gallons": [3]}), b18).passed is True
    assert score(bev_trace({"item": "cambros", "drinks": ["coffee"], "gallons": [3]}), b18).stage == "arguments"
    assert score(bev_trace({"item": "cambros", "drinks": ["coffee"]}), b19).passed is True
    assert score(bev_trace({"item": "cambros", "drinks": ["coffee"], "gallons": [5]}), b19).stage == "arguments"
    assert score(bev_trace({"item": "cambros", "drinks": ["coffee"], "guests": 30}), b19).stage == "arguments"


def test_beverage_amount_not_compared_cases(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13. B9 compares the drink names only (any amount): right drinks with 45 guests pass; one missing drink fails."""
    case = by_id(b_cases, "B9")
    assert score(bev_trace({"item": "cups", "drinks": ["iced water", "orange juice"], "guests": 45}), case).passed is True
    assert score(bev_trace({"item": "cups", "drinks": ["iced water"], "guests": 45}), case).stage == "arguments"


def test_beverage_call_in_a_recipe_case_fails_at_the_router(score, b_cases):
    """Covers: AC-3 (wrong), EC-13. A scale_recipe TOOL part for a beverage case (B1) fails with stage router."""
    t = trace([RoutedPart("TOOL", "q", RECIPE)], [stage("q", call(RECIPE, R3))])
    s = score(t, by_id(b_cases, "B1"))
    assert s.passed is False and s.stage == "router"


def test_b12_checks_the_drinks_argument_and_the_supply_in_the_result(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13, AC-6 (revision 1, B12). Supplies for decaf with no amount and no guests: the call's drinks argument must hold exactly 'decaf' (stripped, any case) and the result must name Stir sticks; another drink, an extra drink or another item fails."""
    case = by_id(b_cases, "B12")
    assert score(bev_trace({"item": "supplies", "drinks": ["decaf"]}), case).passed is True
    assert score(bev_trace({"item": "supplies", "drinks": ["  Decaf "]}), case).passed is True
    assert score(bev_trace({"item": "supplies", "drinks": ["coffee"]}), case).stage == "arguments"
    assert score(bev_trace({"item": "supplies", "drinks": ["decaf", "coffee"]}), case).stage == "arguments"
    assert score(bev_trace({"item": "cups", "drinks": ["decaf"]}), case).stage == "arguments"


def test_b13_checks_the_drinks_argument_and_the_supply_in_the_result(score, b_cases):
    """Covers: AC-3 (right, wrong), EC-13, AC-6 (revision 1, B13). Supplies for hot water: the drinks argument must be exactly 'hot water' and the result must name Tea packets; iced tea (no tea packets) fails."""
    case = by_id(b_cases, "B13")
    assert score(bev_trace({"item": "supplies", "drinks": ["hot water"]}), case).passed is True
    assert score(bev_trace({"item": "supplies", "drinks": ["iced tea"]}), case).stage == "arguments"


def test_b12_b13_guests_given_fail(score, b_cases):
    """Covers: AC-3 (wrong), EC-13 (revision 1). B12 and B13 say no guests: an invented guests=30 fails with stage arguments."""
    assert score(bev_trace({"item": "supplies", "drinks": ["decaf"], "guests": 30}), by_id(b_cases, "B12")).stage == "arguments"
    assert score(bev_trace({"item": "supplies", "drinks": ["hot water"], "guests": 30}), by_id(b_cases, "B13")).stage == "arguments"


# ---------------------------------------------------------------- the case tables themselves

def test_case_tables_have_twenty_cases_each(b_cases, r_cases):
    """Covers: AC-3 (boundary), AC-6, AC-7. The eval has exactly B1 to B20 and R1 to R20, with unique ids, a question and at least one expected call each."""
    assert [c["id"] for c in b_cases] == [f"B{i}" for i in range(1, 21)]
    assert [c["id"] for c in r_cases] == [f"R{i}" for i in range(1, 21)]
    for c in list(b_cases) + list(r_cases):
        assert c["question"].strip() and c["calls"]
    assert all(e["tool"] == BEV for c in b_cases for e in c["calls"])
    assert [e["tool"] for e in by_id(r_cases, "R19")["calls"]] == [RECIPE, BEV]

"""Spec 020, AC-3 (unit side): the case table of section 4.2 and its pass rule.

These unit tests need no Ollama. They check that the 5 cases are the ones in the spec and that the
scoring rule used by the eval (conftest `score_case`) follows "How a case passes".
"""
import pytest

from blc.planner import Plan, PlannedCall

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"


def plan_of(*calls):
    route = "DOCS" if all(c.name == SEARCH for c in calls) else "TOOL"
    return Plan(route=route, calls=tuple(calls), fallback=False)


def bev(item, drinks, guests):
    return PlannedCall(BEV, {"item": item, "drinks": drinks, "guests": guests})


def test_case_table_matches_spec(mixed_cases):
    """Covers: AC-3 (right), section 4.2. X1 to X5: ids, questions, items, drink and guests as in the table."""
    got = [(c["id"], c["question"], sorted(c["expected"]["items"]), c["expected"]["drink"], c["expected"]["guests"])
           for c in mixed_cases]
    assert got == [
        ("X1", "How many gallons and how many cups for iced tea for 90 guests?", ["cups", "gallons"], "iced tea", 90),
        ("X2", "How many cambros and how many cups for coffee for 120 guests?", ["cambros", "cups"], "coffee", 120),
        ("X3", "For 60 guests of peach tea, how many gallons, cambros and cups?",
         ["cambros", "cups", "gallons"], "peach tea", 60),
        ("X4", "How many cups and gallons of decaf do I need for 40 guests?", ["cups", "gallons"], "decaf", 40),
        ("X5", "What do I need in gallons and cups for lemonade for 30 guests?", ["cups", "gallons"], "lemonade", 30),
    ]


def test_t5_question_is_spec_018s(t5_case):
    """Covers: AC-3 (right), section 4.2. T5 is the cups question for iced tea and lemonade at 90 guests."""
    assert t5_case["question"] == "How many cups for iced tea and lemonade for 90 guests?"


def test_exact_plan_passes(mixed_cases, score_case):
    """Covers: AC-3 (right). One call per expected item, right drink and guests: no failed checks (X3, three items)."""
    x3 = mixed_cases[2]
    plan = plan_of(bev("gallons", ["peach tea"], 60), bev("cambros", ["peach tea"], 60), bev("cups", ["peach tea"], 60))
    assert score_case(plan, x3["expected"]) == []


def test_order_and_case_and_spaces_do_not_matter(mixed_cases, score_case):
    """Covers: AC-3 (boundary). Any order; the drink is stripped and compared ignoring case; a string drink works."""
    x1 = mixed_cases[0]
    plan = plan_of(bev("cups", ["  Iced TEA "], 90), bev("gallons", "iced tea", 90))
    assert score_case(plan, x1["expected"]) == []


def test_search_calls_are_ignored(mixed_cases, score_case):
    """Covers: AC-3 (boundary). search_documents calls do not fail a case."""
    x5 = mixed_cases[4]
    plan = plan_of(PlannedCall(SEARCH, {"query": "lemonade"}), bev("gallons", ["lemonade"], 30), bev("cups", ["lemonade"], 30))
    assert score_case(plan, x5["expected"]) == []


def test_missing_item_fails(mixed_cases, score_case):
    """Covers: AC-3 (wrong). Only gallons for a gallons-and-cups question: items fails."""
    plan = plan_of(bev("gallons", ["iced tea"], 90))
    assert "items" in score_case(plan, mixed_cases[0]["expected"])


def test_extra_item_fails(mixed_cases, score_case):
    """Covers: AC-3 (wrong). An extra calculate_bev_item item (supplies) makes the set differ: items fails."""
    plan = plan_of(bev("gallons", ["iced tea"], 90), bev("cups", ["iced tea"], 90), bev("supplies", ["iced tea"], 90))
    assert "items" in score_case(plan, mixed_cases[0]["expected"])


def test_scale_recipe_call_fails(mixed_cases, score_case):
    """Covers: AC-3 (wrong). Any scale_recipe call fails the case."""
    plan = plan_of(bev("gallons", ["iced tea"], 90), bev("cups", ["iced tea"], 90),
                   PlannedCall(REC, {"recipe": "iced tea", "gallons": 4}))
    assert "recipe" in score_case(plan, mixed_cases[0]["expected"])


def test_wrong_drink_fails(mixed_cases, score_case):
    """Covers: AC-3 (wrong). A call naming a different drink, or two drinks, fails on the drink."""
    x1 = mixed_cases[0]["expected"]
    assert "drink" in score_case(plan_of(bev("gallons", ["iced tea"], 90), bev("cups", ["lemonade"], 90)), x1)
    assert "drink" in score_case(plan_of(bev("gallons", ["iced tea", "lemonade"], 90), bev("cups", ["iced tea"], 90)), x1)
    assert "drink" in score_case(plan_of(bev("gallons", [], 90), bev("cups", ["iced tea"], 90)), x1)


def test_wrong_or_missing_guests_fails(mixed_cases, score_case):
    """Covers: AC-3 (wrong, boundary). A guests value that differs by one, or is missing, fails on guests."""
    x2 = mixed_cases[1]["expected"]
    assert "guests" in score_case(plan_of(bev("cambros", ["coffee"], 120), bev("cups", ["coffee"], 119)), x2)
    assert "guests" in score_case(plan_of(bev("cambros", ["coffee"], 120), bev("cups", ["coffee"], None)), x2)


def test_a_plan_with_only_searches_fails(mixed_cases, score_case):
    """Covers: AC-3 (wrong, boundary). A plan with no calculate_bev_item call at all fails on items."""
    plan = plan_of(PlannedCall(SEARCH, {"query": "cups for coffee"}))
    assert "items" in score_case(plan, mixed_cases[3]["expected"])


@pytest.mark.parametrize("case_index", range(5))
def test_every_case_passes_with_its_own_exact_plan(mixed_cases, score_case, case_index):
    """Covers: AC-3 (right). For each of X1 to X5, a plan built from its expectation scores no failures."""
    exp = mixed_cases[case_index]["expected"]
    plan = plan_of(*[bev(i, [exp["drink"]], exp["guests"]) for i in sorted(exp["items"])])
    assert score_case(plan, exp) == []

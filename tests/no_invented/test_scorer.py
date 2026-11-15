"""Spec 021, AC-7b (scorer): the section 4.4 scorer on hand-made outcomes with fake tool results.

The scorer is a pure function of a case, an outcome and a tool-result function (it lives in conftest as the
`scorer` fixture). These tests also check the 30 case table itself (30 cases, 10 per path, ids G/L/B 1-10).
"""
from __future__ import annotations

import pytest

BEV = "calculate_bev_item"
REC = "scale_recipe"

SRC_COFFEE = "data/supplies/coffee.md"
SRC_LEMON = "data/supplies/lemon.md"
SRC_RULES = "data/pull_sheet/rules/beverages.md"


@pytest.fixture
def by_id(golden_cases):
    return {c["id"]: c for c in golden_cases}


def results(res):
    """A tool-result function that always returns res."""
    return lambda name, args: res


# ---------------------------------------------------------------- the case table

def test_case_table_has_30_cases_10_per_path(golden_cases):
    """Covers: AC-7 (right). G1-G10 TOOL, L1-L10 DOCS, B1-B10 BOTH."""
    assert [c["id"] for c in golden_cases] == [f"{p}{i}" for p in "GLB" for i in range(1, 11)]
    for c in golden_cases:
        assert c["path"] == {"G": "TOOL", "L": "DOCS", "B": "BOTH"}[c["id"][0]]


# ---------------------------------------------------------------- part 1, gold call

def good_g1():
    return [(BEV, {"item": "cambros", "drinks": ["Brewed Hot Cider "], "guests": 85})]


def test_part1_pass_with_casefolded_stripped_drinks(scorer, by_id, mkout):
    """Covers: AC-7b (right). Drinks compare stripped and casefolded."""
    assert scorer.part1(by_id["G1"], mkout("TOOL", good_g1())) is True


@pytest.mark.parametrize("args", [
    {"item": "cups", "drinks": ["brewed hot cider"], "guests": 85},        # item
    {"item": "cambros", "drinks": ["coffee"], "guests": 85},               # drinks
    {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 84},     # guests
    {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85, "gallons": [3]},  # extra gallons
    {"item": "cambros", "drinks": ["brewed hot cider"]},                   # missing guests
])
def test_part1_fail_on_each_field(scorer, by_id, mkout, args):
    """Covers: AC-7b (wrong). A different item, drinks, guests or gallons fails part 1."""
    assert scorer.part1(by_id["G1"], mkout("TOOL", [(BEV, args)])) is False


def test_part1_fail_on_wrong_tool_name(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). scale_recipe where calculate_bev_item was expected fails."""
    assert scorer.part1(by_id["G1"], mkout("TOOL", [(REC, {"recipe": "lemonade", "guests": 85})])) is False


def test_part1_fail_on_extra_call(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). An extra call fails: same count is required."""
    calls = good_g1() + [(BEV, {"item": "cups", "drinks": ["decaf"], "guests": 5})]
    assert scorer.part1(by_id["G1"], mkout("TOOL", calls)) is False


def test_part1_fail_on_missing_call(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). No tool ran for a TOOL case."""
    assert scorer.part1(by_id["G1"], mkout("TOOL", [])) is False


def test_part1_drinks_as_a_set_ignores_order(scorer, by_id, mkout):
    """Covers: AC-7b (boundary). G2's two drinks in either order match."""
    for drinks in (["orange juice", "decaf"], ["decaf", "orange juice"]):
        out = mkout("TOOL", [(BEV, {"item": "cups", "drinks": drinks, "guests": 140})])
        assert scorer.part1(by_id["G2"], out) is True


def test_part1_numbers_by_value(scorer, by_id, mkout):
    """Covers: AC-7b (boundary). 85.0 and '85' equal 85; a bool never counts as a number."""
    for g in (85.0, "85"):
        out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": g})])
        assert scorer.part1(by_id["G1"], out) is True
    out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": True})])
    assert scorer.part1(by_id["G1"], out) is False


def test_part1_gallons_list_compared_by_value(scorer, by_id, mkout):
    """Covers: AC-7b (boundary). G4 gold gallons [9]: [9.0] and ['9'] match; empty or [8] do not."""
    def out(g):
        return mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["iced tea"], "gallons": g})])
    assert scorer.part1(by_id["G4"], out([9.0])) is True
    assert scorer.part1(by_id["G4"], out(["9"])) is True
    assert scorer.part1(by_id["G4"], out([8])) is False
    assert scorer.part1(by_id["G4"], out([])) is False
    assert scorer.part1(by_id["G4"], out(None)) is False


def test_part1_recipe_gallons_one_item_list_counts_as_number(scorer, by_id, mkout):
    """Covers: AC-7b (boundary). G6 gold gallons 2.5: a list [2.5] matches; 2 does not."""
    def out(g):
        return mkout("TOOL", [(REC, {"recipe": " Lemonade ", "gallons": g})])
    assert scorer.part1(by_id["G6"], out(2.5)) is True
    assert scorer.part1(by_id["G6"], out([2.5])) is True
    assert scorer.part1(by_id["G6"], out(2)) is False


def test_part1_recipe_with_extra_guests_fails(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). G6 has no gold guests: a run guests value differs."""
    out = mkout("TOOL", [(REC, {"recipe": "lemonade", "gallons": 2.5, "guests": 40})])
    assert scorer.part1(by_id["G6"], out) is False


@pytest.mark.parametrize("args", [
    {"item": "cambros", "drinks": ["coffee"], "gallons": [4]},
    {"item": "cambros", "drinks": ["coffee"], "guests": 100},
    {"item": "cambros", "drinks": ["coffee"], "gallons": [4], "guests": 100},
])
def test_part1_any_of_alternatives_pass(scorer, by_id, mkout, args):
    """Covers: AC-7b (right). Each of G9's three alternative gold calls passes."""
    assert scorer.part1(by_id["G9"], mkout("TOOL", [(BEV, args)])) is True


def test_part1_any_of_rejects_a_mix(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). Gallons 4 with guests 50 matches none of the alternatives."""
    args = {"item": "cambros", "drinks": ["coffee"], "gallons": [4], "guests": 50}
    assert scorer.part1(by_id["G9"], mkout("TOOL", [(BEV, args)])) is False


def test_part1_docs_case_with_tool_result_fails(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). A DOCS case has no gold calls: any tool result fails part 1."""
    out = mkout("DOCS", [(BEV, {"item": "cups", "guests": 5})], searches=[("q", [SRC_COFFEE])])
    assert scorer.part1(by_id["L1"], out) is False


def test_part1_docs_case_without_tools_passes(scorer, by_id, mkout):
    """Covers: AC-7b (right). A DOCS case with no tool result passes part 1."""
    assert scorer.part1(by_id["L1"], mkout("DOCS", [], searches=[("q", [SRC_COFFEE])])) is True


# ---------------------------------------------------------------- part 2, invented numbers

def test_part2_pass_when_all_values_allowed(scorer, by_id, mkout):
    """Covers: AC-7b (right). guests 85 is in the question."""
    assert scorer.part2(by_id["G1"], mkout("TOOL", good_g1())) is True


def test_part2_fail_on_invented_value(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). gallons [6] is not in G1's question."""
    out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85, "gallons": [6]})])
    assert scorer.part2(by_id["G1"], out) is False


def test_part2_history_numbers_allowed(scorer, by_id, mkout):
    """Covers: AC-7b (right). G9's gallons [4] and guests 100 come from the history."""
    out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["coffee"], "gallons": [4], "guests": 100})])
    assert scorer.part2(by_id["G9"], out) is True


def test_part2_number_words_allowed(scorer, by_id, mkout):
    """Covers: AC-7b (right). G7 'twenty-five guests' allows 25."""
    out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["hot water"], "guests": 25})])
    assert scorer.part2(by_id["G7"], out) is True
    out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["hot water"], "guests": 5})])
    assert scorer.part2(by_id["G7"], out) is False


def test_part2_dropped_value_counts_as_not_invented(scorer, by_id, mkout):
    """Covers: AC-7b (right). The first plan invented gallons, but the run call (after the drop) has none:
    part 2 passes, and the invention is only reported."""
    rejected = [object()]
    out = mkout("TOOL", good_g1(), rejected=rejected, retried=True)
    assert scorer.part2(by_id["G1"], out) is True
    s = scorer.score(by_id["G1"], out, results(None_res_ok_g1()))
    assert s["part2"] is True
    assert s["first_invented"] is True
    assert s["retried"] is True


def test_part2_non_numbers_and_one_not_scored(scorer, by_id, mkout):
    """Covers: AC-7b (boundary). 'lots', null and the free number 1 are not invented."""
    for g in ("lots", None, [1]):
        out = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["coffee"], "guests": 85, "gallons": g})])
        assert scorer.part2(by_id["G1"], out) is True


# ---------------------------------------------------------------- part 3, tool facts

def None_res_ok_g1(mkres=None):
    from types import SimpleNamespace as NS
    return NS(status="ok", drinks=[NS(drink="Brewed hot cider", amount=3)],
              lines=[NS(supply="5 gal cambro", quantity=1)])


def test_part3_pass_tool_case(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (right). Status ok, drink with gallons and exact lines."""
    res = mkres.bev([("Brewed hot cider", 3)], [("5 gal cambro", 1)])
    assert scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), results(res)) is True


@pytest.mark.parametrize("res_args", [
    dict(drinks=[("Brewed hot cider", 4)], lines=[("5 gal cambro", 1)]),               # wrong gallons
    dict(drinks=[("Coffee", 3)], lines=[("5 gal cambro", 1)]),                         # wrong drink
    dict(drinks=[("Brewed hot cider", 3)], lines=[("5 gal cambro", 2)]),               # wrong quantity
    dict(drinks=[("Brewed hot cider", 3)], lines=[("2 gal cambro", 1)]),               # wrong supply
    dict(drinks=[("Brewed hot cider", 3)], lines=[("5 gal cambro", 1)], status="need_info"),
])
def test_part3_fail_tool_case(scorer, by_id, mkout, mkres, res_args):
    """Covers: AC-7b (wrong). A wrong drink, gallons, line or status fails part 3."""
    res = mkres.bev(**res_args)
    assert scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), results(res)) is False


def test_part3_cambros_lines_must_be_exact(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (boundary). For cambros an extra line fails (exact equality)."""
    res = mkres.bev([("Brewed hot cider", 3)], [("5 gal cambro", 1), ("1 gal cambro", 1)])
    assert scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), results(res)) is False


def test_part3_cups_lines_must_be_exact(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (boundary). G2 (cups): both lines pass in either order; a missing or extra line fails."""
    args = {"item": "cups", "drinks": ["orange juice", "decaf"], "guests": 140}
    drinks = [("Orange juice", 6), ("Decaf", 6)]
    both = mkres.bev(drinks, [("cold-cups", 240), ("hot-cups", 240)])
    missing = mkres.bev(drinks, [("hot-cups", 240)])
    extra = mkres.bev(drinks, [("hot-cups", 240), ("cold-cups", 240), ("Sugar", 1)])
    out = mkout("TOOL", [(BEV, args)])
    assert scorer.part3(by_id["G2"], out, results(both)) is True
    assert scorer.part3(by_id["G2"], out, results(missing)) is False
    assert scorer.part3(by_id["G2"], out, results(extra)) is False


def test_part3_everything_lines_are_a_subset_check(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (boundary). For everything, extra lines are fine; a missing required line fails."""
    args = {"item": "everything", "drinks": ["decaf"], "guests": 55}
    need = [("2 gal cambro", 1), ("hot-cups", 105), ("Stir sticks", 1), ("Sugar", 1)]
    out = mkout("TOOL", [(BEV, args)])
    full = mkres.bev([("Decaf", 2)], need + [("Creamer", 2)])
    short = mkres.bev([("Decaf", 2)], need[:-1])
    assert scorer.part3(by_id["G8"], out, results(full)) is True
    assert scorer.part3(by_id["G8"], out, results(short)) is False


def test_part3_gallons_item_needs_empty_lines(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (boundary). For item gallons, lines must be empty."""
    args = {"item": "gallons", "drinks": ["iced water"], "guests": 210}
    out = mkout("TOOL", [(BEV, args)])
    assert scorer.part3(by_id["G3"], out, results(mkres.bev([("Iced water", 8)], []))) is True
    assert scorer.part3(by_id["G3"], out, results(mkres.bev([("Iced water", 8)], [("5 gal cambro", 2)]))) is False


def test_part3_recipe_pass_and_fail(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (right/wrong). G5 needs 2 gallons and 14 oz concentrate."""
    out = mkout("TOOL", [(REC, {"recipe": "lemonade", "guests": 45})])
    assert scorer.part3(by_id["G5"], out, results(mkres.rec(2, 14))) is True
    assert scorer.part3(by_id["G5"], out, results(mkres.rec(2, 15))) is False
    assert scorer.part3(by_id["G5"], out, results(mkres.rec(3, 14))) is False
    assert scorer.part3(by_id["G5"], out, results(mkres.rec(2, 14, status="invalid"))) is False


def test_part3_tool_case_without_a_tool_result_fails(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (wrong). A TOOL case where no tool ran cannot pass part 3."""
    assert scorer.part3(by_id["G1"], mkout("DOCS", []), results(mkres.bev([("Brewed hot cider", 3)], []))) is False


def test_part3_tool_function_gets_the_run_args(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (right). The tool-result function is called with the name and the args that ran."""
    seen = []

    def fn(name, args):
        seen.append((name, dict(args)))
        return mkres.bev([("Brewed hot cider", 3)], [("5 gal cambro", 1)])

    scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), fn)
    assert seen == [(BEV, good_g1()[0][1])]


# ---------------------------------------------------------------- part 3, documents

def test_part3_docs_pass(scorer, by_id, mkout):
    """Covers: AC-7b (right). The required document is among the retrieved sources."""
    out = mkout("DOCS", [], searches=[("coffee", [SRC_LEMON, SRC_COFFEE])])
    assert scorer.part3(by_id["L1"], out, results(None)) is True


def test_part3_docs_fail_wrong_document(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). The required document is not retrieved."""
    out = mkout("DOCS", [], searches=[("coffee", [SRC_LEMON])])
    assert scorer.part3(by_id["L1"], out, results(None)) is False


def test_part3_docs_fail_without_a_search(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). No search ran."""
    assert scorer.part3(by_id["L1"], mkout("DOCS", []), results(None)) is False


def test_part3_docs_found_in_second_search(scorer, by_id, mkout):
    """Covers: AC-7b (right). The required document comes back from the second of two searches."""
    out = mkout("DOCS", [], searches=[("a", [SRC_LEMON]), ("b", [SRC_COFFEE])])
    assert scorer.part3(by_id["L1"], out, results(None)) is True


def test_part3_docs_any_of(scorer, by_id, mkout):
    """Covers: AC-7b (right). B6 accepts the rules file or the lemon file."""
    for src in (SRC_RULES, SRC_LEMON):
        out = mkout("BOTH", good_b6(), searches=[("q", [src])])
        assert scorer.part3(by_id["B6"], out, results(b6_res())) is True


def good_b6():
    return [(BEV, {"item": "cups", "drinks": ["hot water"], "guests": 35})]


def b6_res():
    from types import SimpleNamespace as NS
    return NS(status="ok", drinks=[NS(drink="Hot water", amount=1)], lines=[NS(supply="hot-cups", quantity=55)])


def test_part3_both_needs_tool_and_document(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). BOTH fails when only one half holds."""
    no_doc = mkout("BOTH", good_b6(), searches=[("q", [SRC_COFFEE])])
    assert scorer.part3(by_id["B6"], no_doc, results(b6_res())) is False
    bad_tool = mkout("BOTH", good_b6(), searches=[("q", [SRC_RULES])])
    from types import SimpleNamespace as NS
    wrong = NS(status="ok", drinks=[NS(drink="Hot water", amount=2)], lines=[NS(supply="hot-cups", quantity=55)])
    assert scorer.part3(by_id["B6"], bad_tool, results(wrong)) is False


# ---------------------------------------------------------------- the whole case

def full_good_b6(mkout, **kw):
    return mkout("BOTH", good_b6(), searches=[("q", [SRC_RULES])], **kw)


def test_case_passes_when_everything_holds(scorer, by_id, mkout):
    """Covers: AC-7b (right). Route right, parts 1, 2 and 3 pass: the case passes."""
    s = scorer.score(by_id["B6"], full_good_b6(mkout), results(b6_res()))
    assert s["passed"] is True
    assert (s["part1"], s["part2"], s["part3"]) == (True, True, True)
    assert s["retried"] is False and s["first_invented"] is False


def test_case_fails_on_wrong_route(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). Everything right but the route is DOCS: fail."""
    out = mkout("DOCS", good_b6(), searches=[("q", [SRC_RULES])])
    assert scorer.score(by_id["B6"], out, results(b6_res()))["passed"] is False


def test_tool_case_with_a_search_fails(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). A TOOL case must have no search, even when parts 1 to 3 pass."""
    out = mkout("TOOL", good_g1(), searches=[("q", [SRC_COFFEE])])
    res = None_res_ok_g1()
    assert scorer.score(by_id["G1"], out, results(res))["passed"] is False
    clean = mkout("TOOL", good_g1())
    assert scorer.score(by_id["G1"], clean, results(res))["passed"] is True


def test_case_fails_when_a_single_part_fails(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). Each part failing alone fails the case."""
    res = None_res_ok_g1()
    p1 = mkout("TOOL", [(BEV, {"item": "cups", "drinks": ["brewed hot cider"], "guests": 85})])
    s = scorer.score(by_id["G1"], p1, results(res))
    assert s["part1"] is False and s["passed"] is False
    p2 = mkout("TOOL", [(BEV, {"item": "cambros", "drinks": ["brewed hot cider"], "guests": 85, "gallons": [6]})])
    s = scorer.score(by_id["G1"], p2, results(res))
    assert s["part2"] is False and s["passed"] is False
    s = scorer.score(by_id["G1"], mkout("TOOL", good_g1()), results(None_res_ok_g1_wrong()))
    assert s["part3"] is False and s["passed"] is False


def None_res_ok_g1_wrong():
    from types import SimpleNamespace as NS
    return NS(status="ok", drinks=[NS(drink="Brewed hot cider", amount=9)], lines=[NS(supply="5 gal cambro", quantity=1)])


# ---------------------------------------------------------------- Fraction amounts (revision 1)
# The real tools return amounts as fractions.Fraction (DrinkAmount.amount, RecipeResult.gallons,
# ScaledIngredient.amount). The scorer must compare them by value.

def test_num_accepts_fraction_and_any_real_by_value(scorer):
    """Covers: AC-7b (right), revision 1. Fraction, int, float and numeric strings compare equal by value;
    bools and non-numbers are never numbers."""
    from fractions import Fraction

    num = scorer.num
    assert num(Fraction(35, 2)) == num(17.5) == num(Fraction("17.5")) == num("17.5")
    assert num(Fraction(3)) is not None and num(Fraction(3)) == num(3)
    assert num(Fraction(7, 2)) != num(3)
    assert num(True) is None and num(False) is None
    assert num("lots") is None and num(None) is None and num([3]) is None


def test_part3_fraction_amounts_pass_bev(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (right), revision 1. Drink gallons and line quantities as Fraction (real shape) pass."""
    from fractions import Fraction

    res = mkres.bev([("Brewed hot cider", Fraction(3))], [("5 gal cambro", Fraction(1))])
    assert scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), results(res)) is True


def test_part3_fraction_amounts_fail_bev_on_wrong_value(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (wrong), revision 1. A Fraction that differs by value fails (3 gal required, 7/2 given)."""
    from fractions import Fraction

    res = mkres.bev([("Brewed hot cider", Fraction(7, 2))], [("5 gal cambro", Fraction(1))])
    assert scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), results(res)) is False
    res = mkres.bev([("Brewed hot cider", Fraction(3))], [("5 gal cambro", Fraction(2))])
    assert scorer.part3(by_id["G1"], mkout("TOOL", good_g1()), results(res)) is False


def test_part3_fraction_recipe_pass(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (right), revision 1. G6: gallons Fraction(5, 2) and concentrate Fraction(35, 2) oz pass."""
    from fractions import Fraction

    out = mkout("TOOL", [(REC, {"recipe": "lemonade", "gallons": 2.5})])
    assert scorer.part3(by_id["G6"], out, results(mkres.rec(Fraction(5, 2), Fraction(35, 2)))) is True


def test_part3_fraction_recipe_fail_on_wrong_value(scorer, by_id, mkout, mkres):
    """Covers: AC-7b (wrong), revision 1. G6 with concentrate 17 oz or gallons 3 as Fractions fails."""
    from fractions import Fraction

    out = mkout("TOOL", [(REC, {"recipe": "lemonade", "gallons": 2.5})])
    assert scorer.part3(by_id["G6"], out, results(mkres.rec(Fraction(5, 2), Fraction(17)))) is False
    assert scorer.part3(by_id["G6"], out, results(mkres.rec(Fraction(3), Fraction(35, 2)))) is False


def test_docs_case_with_a_tool_result_fails_the_case(scorer, by_id, mkout):
    """Covers: AC-7b (wrong). A DOCS case whose turn ran a tool fails, though the document was found."""
    out = mkout("DOCS", [(BEV, {"item": "cups", "guests": 5})], searches=[("q", [SRC_COFFEE])])
    s = scorer.score(by_id["L1"], out, results(None))
    assert s["part1"] is False and s["passed"] is False

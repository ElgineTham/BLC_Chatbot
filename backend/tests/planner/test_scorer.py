"""Spec 018, AC-6 (EC-14 to EC-18) and NFR-4/NFR-7: the pure scorer, on hand-made plans. No model.

`score(case, plan)` returns the set of failed checks, a subset of {"route", "tools", "search"}.
"""
import pytest

from blc.planner import PLANNER_PROMPT, SEARCH_TOOL, Plan, PlannedCall

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"


def S(query):
    return PlannedCall(SEARCH, {"query": query})


def B(**args):
    return PlannedCall(BEV, args)


def R(**args):
    return PlannedCall(REC, args)


def plan(route, *calls):
    return Plan(route, tuple(calls), False)


M1_TOOL = dict(item="cambros", drinks=["Iced Tea "], gallons=[6.0])
M1_SEARCH = "Where are the cambros kept?"


def t1_plan(gallons=(7, 3), drinks=("peach tea", "hot water"), **extra):
    return plan("TOOL", B(item="cambros", drinks=list(drinks), gallons=list(gallons), **extra))


# --------------------------------------------------------------------------
# EC-14: passing plans
# --------------------------------------------------------------------------

def test_m1_passes(score, cases):
    """Covers: AC-6 (right), EC-14. M1 search + cambros call (case, spacing, 6.0) passes."""
    assert score(cases["M1"], plan("BOTH", S(M1_SEARCH), B(**M1_TOOL))) == set()


def test_m1_order_does_not_matter(score, cases):
    """Covers: AC-6 (right), EC-14. The same calls in the other order pass."""
    assert score(cases["M1"], plan("BOTH", B(**M1_TOOL), S(M1_SEARCH))) == set()


EXPECTED_TOOL_PLANS = {
    "T1": plan("TOOL", B(item="cambros", drinks=["peach tea", "hot water"], gallons=[7, 3])),
    "T2": plan("TOOL", B(item="gallons", drinks=["coffee"], guests=160)),
    "T3": plan("TOOL", B(item="cups", guests=45)),
    "T4": plan("TOOL", B(item="everything", drinks=["orange juice"], gallons=[6])),
    "T5": plan("TOOL", B(item="cups", drinks=["iced tea", "lemonade"], guests=90)),
    "T6": plan("TOOL", R(recipe="lemonade")),
    "T7": plan("TOOL", R(recipe="lemonade", guests=60)),
    "T8": plan("TOOL", R(recipe="lemonade", gallons=4),
               B(item="cambros", drinks=["lemonade"], gallons=[4])),
    "T9": plan("TOOL", B(item="cambros", drinks=["brewed hot cider"], guests=75)),
    "T10": plan("TOOL", B(item="cambros", drinks=["coffee", "decaf"], gallons=[5, 5])),
}


@pytest.mark.parametrize("cid", sorted(EXPECTED_TOOL_PLANS))
def test_tool_cases_have_a_reachable_pass(score, cases, cid):
    """Covers: AC-6 (right), EC-14. Each TOOL case passes with its expected calls and fails if the calls are dropped."""
    assert score(cases[cid], EXPECTED_TOOL_PLANS[cid]) == set()
    assert "tools" in score(cases[cid], plan("TOOL"))


@pytest.mark.parametrize("cid, query", [
    ("D1", "supplies to bring for coffee and hot water"),
    ("D2", "should I bring lemons for the iced tea"),
    ("D3", "where do the 5 gallon cambros go"),
    ("D4", "is lemonade served in a cambro"),
    ("D5", "what flavors of syrup do we have"),
    ("D6", "what to bring for coffee, iced water and hot water"),
    ("D7", "what is in the coffee, decaf, tea, iced water and juice package"),
    ("D8", "how to pull stock of concentrates"),
    ("D9", "when do we bring hot cups"),
    ("D10", "backup if the syrups are not there"),
    ("D10", "syrups not found"),
])
def test_docs_cases_have_a_reachable_pass(score, cases, cid, query):
    """Covers: AC-6 (right), EC-14. Each DOCS case passes with one good search and no tool call."""
    assert score(cases[cid], plan("DOCS", S(query))) == set()


# --------------------------------------------------------------------------
# EC-15: route / search / tools failures
# --------------------------------------------------------------------------

def test_wrong_route_and_missing_search_fail(score, cases):
    """Covers: AC-6 (wrong), EC-15. M1's calls without the search fail on route and search."""
    failed = score(cases["M1"], plan("TOOL", B(**M1_TOOL)))
    assert {"route", "search"} <= failed
    assert "tools" not in failed


def test_docs_case_with_extra_tool_fails_tools(score, cases):
    """Covers: AC-6 (wrong), EC-15. A DOCS case with a tool call fails on tools."""
    p = plan("BOTH", S("where is the coffee"), B(item="gallons", drinks=["coffee"]))
    assert "tools" in score(cases["D1"], p)


def test_tool_case_with_extra_search_fails_search(score, cases):
    """Covers: AC-6 (wrong), EC-15. A TOOL case with a search fails on search."""
    p = plan("BOTH", S("how many cups"), B(item="cups", guests=45))
    failed = score(cases["T3"], p)
    assert "search" in failed
    assert "tools" not in failed


def test_docs_case_without_search_fails(score, cases):
    """Covers: AC-6 (wrong), EC-15. A DOCS case with no search at all fails search."""
    assert "search" in score(cases["D1"], plan("DOCS"))


def test_docs_case_with_tool_instead_of_search_fails_route(score, cases):
    """Covers: AC-6 (wrong), EC-15. D2 answered with a tool call only fails route, tools and search."""
    p = plan("TOOL", B(item="supplies", drinks=["iced tea"]))
    assert score(cases["D2"], p) == {"route", "tools", "search"}


# --------------------------------------------------------------------------
# EC-16: tool-call mismatches
# --------------------------------------------------------------------------

def test_wrong_item_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. Wrong item fails tools."""
    p = plan("TOOL", B(item="gallons", drinks=["peach tea", "hot water"], gallons=[7, 3]))
    assert "tools" in score(cases["T1"], p)


def test_pull_sheet_item_must_be_everything(score, cases):
    """Covers: AC-6 (wrong), EC-16. T4 expects item 'everything'; 'supplies' fails."""
    p = plan("TOOL", B(item="supplies", drinks=["orange juice"], gallons=[6]))
    assert "tools" in score(cases["T4"], p)


def test_missing_drink_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. A missing drink fails tools."""
    p = plan("TOOL", B(item="cambros", drinks=["peach tea"], gallons=[7]))
    assert "tools" in score(cases["T1"], p)


def test_extra_drink_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. An extra drink fails tools."""
    p = plan("TOOL", B(item="cambros", drinks=["peach tea", "hot water", "coffee"], gallons=[7, 3, 3]))
    assert "tools" in score(cases["T1"], p)


def test_swapped_gallons_fail(score, cases):
    """Covers: AC-6 (wrong), EC-16. T1 with [3, 7] for peach tea, hot water fails."""
    assert "tools" in score(cases["T1"], t1_plan(gallons=(3, 7)))


def test_gallons_in_other_drink_order_pass(score, cases):
    """Covers: AC-6 (right), EC-16. Pairs, not positions: hot water first with [3, 7] passes."""
    assert score(cases["T1"], t1_plan(gallons=(3, 7), drinks=("hot water", "peach tea"))) == set()


def test_invented_guests_fail(score, cases):
    """Covers: AC-6 (wrong), EC-16. T1 with an extra guests 60 fails."""
    assert "tools" in score(cases["T1"], t1_plan(guests=60))


def test_guest_count_turned_into_gallons_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. T9 (guests only) with gallons instead of guests fails."""
    p = plan("TOOL", B(item="cambros", drinks=["brewed hot cider"], gallons=[75]))
    assert "tools" in score(cases["T9"], p)


def test_missing_call_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. T8 with only the recipe call fails."""
    assert "tools" in score(cases["T8"], plan("TOOL", R(recipe="lemonade", gallons=4)))


def test_extra_call_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. T6 with an extra tool call fails."""
    p = plan("TOOL", R(recipe="lemonade"), B(item="everything", drinks=["lemonade"]))
    assert "tools" in score(cases["T6"], p)


def test_recipe_gallons_two_item_list_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. A scale_recipe call with gallons [4, 4] fails T8."""
    p = plan("TOOL", R(recipe="lemonade", gallons=[4, 4]),
             B(item="cambros", drinks=["lemonade"], gallons=[4]))
    assert "tools" in score(cases["T8"], p)


def test_invented_gallons_fail(score, cases):
    """Covers: AC-6 (wrong), EC-16. T7 (guests only) with invented gallons fails."""
    p = plan("TOOL", R(recipe="lemonade", gallons=10, guests=60))
    assert "tools" in score(cases["T7"], p)


def test_wrong_guests_fail(score, cases):
    """Covers: AC-6 (wrong), EC-16. T2 with guests 16 instead of 160 fails."""
    assert "tools" in score(cases["T2"], plan("TOOL", B(item="gallons", drinks=["coffee"], guests=16)))


def test_wrong_tool_name_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. A bev call where a recipe call is expected fails."""
    assert "tools" in score(cases["T6"], plan("TOOL", B(item="everything", drinks=["lemonade"])))


def test_wrong_recipe_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. Wrong recipe name fails."""
    assert "tools" in score(cases["T6"], plan("TOOL", R(recipe="iced tea")))


def test_gallons_count_neither_one_nor_drinks_fails(score, cases):
    """Covers: AC-6 (boundary), EC-16. Three numbers for two drinks is a mismatch."""
    p = plan("TOOL", B(item="cambros", drinks=["coffee", "decaf"], gallons=[5, 5, 5]))
    assert "tools" in score(cases["T10"], p)


def test_non_numeric_gallons_fail(score, cases):
    """Covers: AC-6 (wrong), EC-16. A non-numeric gallons string is a mismatch."""
    p = plan("TOOL", B(item="everything", drinks=["orange juice"], gallons=["six"]))
    assert "tools" in score(cases["T4"], p)


def test_m3_tool_part_sent_to_wrong_tool_fails(score, cases):
    """Covers: AC-6 (wrong), EC-16. M3 with calculate_bev_item gallons [3] for lemonade instead of scale_recipe fails tools."""
    p = plan("BOTH", S("where is the lemon concentrate kept"),
             B(item="gallons", drinks=["lemonade"], gallons=[3]))
    assert "tools" in score(cases["M3"], p)


def test_m3_right_tool_passes(score, cases):
    """Covers: AC-6 (right), EC-16. M3 with scale_recipe lemonade 3 and a concentrate-location search passes."""
    p = plan("BOTH", S("where is the lemon concentrate kept"), R(recipe="lemonade", gallons=3))
    assert score(cases["M3"], p) == set()


def test_two_identical_tool_calls_do_not_match_one_expected(score, cases):
    """Covers: AC-6 (wrong), EC-16. Each expected call matches exactly one actual call: a duplicate is extra."""
    p = plan("TOOL", R(recipe="lemonade"), R(recipe="lemonade"))
    assert "tools" in score(cases["T6"], p)


# --------------------------------------------------------------------------
# EC-17: equivalences
# --------------------------------------------------------------------------

def test_single_number_applies_to_each_drink(score, cases):
    """Covers: AC-6 (right), EC-17. gallons [5] for two drinks equals [5, 5]."""
    p = plan("TOOL", B(item="cambros", drinks=["coffee", "decaf"], gallons=[5]))
    assert score(cases["T10"], p) == set()


@pytest.mark.parametrize("gallons", [[], None, "missing"])
def test_empty_null_missing_gallons_mean_none(score, cases, gallons):
    """Covers: AC-6 (right), EC-17. [] / null / missing gallons all mean no gallons."""
    args = {"item": "cups", "drinks": ["iced tea", "lemonade"], "guests": 90}
    if gallons != "missing":
        args["gallons"] = gallons
    assert score(cases["T5"], plan("TOOL", PlannedCall(BEV, args))) == set()


def test_gallons_where_none_expected_fail(score, cases):
    """Covers: AC-6 (wrong), EC-17. An invented gallons value fails when none was asked."""
    p = plan("TOOL", B(item="cups", drinks=["iced tea", "lemonade"], gallons=[5], guests=90))
    assert "tools" in score(cases["T5"], p)


def test_null_guests_means_none(score, cases):
    """Covers: AC-6 (right), EC-17. guests null equals no guests."""
    p = plan("TOOL", B(item="everything", drinks=["orange juice"], gallons=[6], guests=None))
    assert score(cases["T4"], p) == set()


def test_missing_guests_where_expected_fail(score, cases):
    """Covers: AC-6 (wrong), EC-17. T3 expects guests 45; none given fails."""
    assert "tools" in score(cases["T3"], plan("TOOL", B(item="cups")))


def test_numeric_string_equals_number(score, cases):
    """Covers: AC-6 (right), EC-17. gallons ['6'] equals [6]; guests '45' equals 45."""
    p = plan("BOTH", S(M1_SEARCH), B(item="cambros", drinks=["iced tea"], gallons=["6"]))
    assert score(cases["M1"], p) == set()
    assert score(cases["T3"], plan("TOOL", B(item="cups", guests="45"))) == set()


def test_int_equals_float(score, cases):
    """Covers: AC-6 (right), EC-17. 160 == 160.0."""
    p = plan("TOOL", B(item="gallons", drinks=["coffee"], guests=160.0))
    assert score(cases["T2"], p) == set()


@pytest.mark.parametrize("gallons", [4, 4.0, [4], "4"])
def test_recipe_gallons_forms_equal(score, cases, gallons):
    """Covers: AC-6 (right), EC-17. scale_recipe gallons 4, 4.0, [4] all equal 4."""
    p = plan("TOOL", R(recipe="lemonade", gallons=gallons),
             B(item="cambros", drinks=["lemonade"], gallons=[4]))
    assert score(cases["T8"], p) == set()


@pytest.mark.parametrize("gallons", [[], None, "missing"])
def test_recipe_null_empty_or_missing_gallons_mean_none(score, cases, gallons):
    """Covers: AC-6 (right), EC-17. scale_recipe gallons [] / null / missing equal none (T6)."""
    args = {"recipe": "lemonade"}
    if gallons != "missing":
        args["gallons"] = gallons
    assert score(cases["T6"], plan("TOOL", PlannedCall(REC, args))) == set()


def test_booleans_are_not_numbers(score):
    """Covers: AC-6 (wrong), EC-17. True never equals 1, in guests, drink gallons or recipe gallons."""
    def case(call):
        return {"route": "TOOL", "tools": [call], "keep": [], "drop": []}

    bev_case = case({"name": BEV, "item": "cups", "drinks": ["coffee"], "gallons": [1], "guests": 1})
    assert score(bev_case, plan("TOOL", B(item="cups", drinks=["coffee"], gallons=[1], guests=1.0))) == set()
    assert "tools" in score(bev_case, plan("TOOL", B(item="cups", drinks=["coffee"], gallons=[1], guests=True)))
    assert "tools" in score(bev_case, plan("TOOL", B(item="cups", drinks=["coffee"], gallons=[True], guests=1)))
    rec_case = case({"name": REC, "recipe": "lemonade", "gallons": 1, "guests": None})
    assert score(rec_case, plan("TOOL", R(recipe="lemonade", gallons=1))) == set()
    assert "tools" in score(rec_case, plan("TOOL", R(recipe="lemonade", gallons=True)))


def test_unknown_keys_ignored(score, cases):
    """Covers: AC-6 (right), EC-17. Unlisted keys do not matter."""
    p = plan("TOOL", B(item="cups", guests=45, note="hello", extra=[1]))
    assert score(cases["T3"], p) == set()


def test_drink_case_and_spaces_ignored(score, cases):
    """Covers: AC-6 (right), EC-17. Drink names compare stripped and casefolded."""
    p = plan("TOOL", B(item="everything", drinks=["  ORANGE Juice"], gallons=[6]))
    assert score(cases["T4"], p) == set()


def test_recipe_case_and_spaces_ignored(score, cases):
    """Covers: AC-6 (right), EC-17. Recipe names compare stripped and casefolded."""
    assert score(cases["T6"], plan("TOOL", R(recipe=" Lemonade "))) == set()


def test_cups_with_drink_fails_when_none_expected(score, cases):
    """Covers: AC-6 (wrong), EC-17. T3 expects no drinks; naming one fails."""
    assert "tools" in score(cases["T3"], plan("TOOL", B(item="cups", drinks=["coffee"], guests=45)))


def test_null_or_empty_drinks_mean_no_drinks(score, cases):
    """Covers: AC-6 (right), EC-17. A missing, null or empty drinks list means no drinks (T3)."""
    for extra in ({}, {"drinks": None}, {"drinks": []}):
        assert score(cases["T3"], plan("TOOL", B(item="cups", guests=45, **extra))) == set()


# --------------------------------------------------------------------------
# EC-18: search checks
# --------------------------------------------------------------------------

def test_stem_term_matches_storage(score, cases):
    """Covers: AC-6 (right), EC-18. 'cambro storage' satisfies LOC through 'stor'."""
    p = plan("BOTH", S("cambro storage"), B(**M1_TOOL))
    assert score(cases["M1"], p) == set()


def test_missing_keep_group_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. Query 'iced tea' has neither cambro nor LOC: fails search."""
    failed = score(cases["M1"], plan("BOTH", S("iced tea"), B(**M1_TOOL)))
    assert "search" in failed


def test_one_missing_group_of_two_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. 'cambro' present but no LOC term fails search."""
    failed = score(cases["M1"], plan("BOTH", S("cambro"), B(**M1_TOOL)))
    assert "search" in failed


def test_drop_term_present_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. A query containing the amount 6 fails."""
    p = plan("BOTH", S("where are the cambros for 6 gallons"), B(**M1_TOOL))
    assert "search" in score(cases["M1"], p)


def test_drop_number_is_whole_word(score, cases):
    """Covers: AC-6 (boundary), EC-18. Drop term 6 does not match 16."""
    p = plan("BOTH", S("where are the cambros kept for 16 gallons"), B(**M1_TOOL))
    assert score(cases["M1"], p) == set()


def test_m5_lost_meaning_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. M5 query 'what do I need to bring' lacks 'coffee': fails search."""
    tool = B(item="cambros", drinks=["coffee"], gallons=[3])
    p = plan("BOTH", S("what do I need to bring"), tool)
    assert score(cases["M5"], p) == {"search"}


def test_m5_meaning_kept_passes(score, cases):
    """Covers: AC-6 (right), EC-18. M5 query 'what to bring for coffee' passes."""
    tool = B(item="cambros", drinks=["coffee"], gallons=[3])
    assert score(cases["M5"], plan("BOTH", S("what to bring for coffee"), tool)) == set()


def test_m5_amount_in_query_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. M5 query carrying '3 gallons' hits the drop term 3."""
    tool = B(item="cambros", drinks=["coffee"], gallons=[3])
    p = plan("BOTH", S("what to bring for 3 gallons of coffee"), tool)
    assert "search" in score(cases["M5"], p)


def test_m8_amount_in_query_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. M8 query that carries the tool part's amount '40' fails search."""
    p = plan("BOTH", S("Do we bring lemons for peach tea for 40 guests"),
             B(item="cups", drinks=["peach tea"], guests=40))
    assert "search" in score(cases["M8"], p)


def test_keep_groups_checked_across_searches_joined(score, cases):
    """Covers: AC-6 (right), EC-18. Keep terms may be spread over several searches."""
    p = plan("BOTH", S("cambro"), S("where kept"), B(**M1_TOOL))
    assert score(cases["M1"], p) == set()


def test_drop_checked_in_any_query(score, cases):
    """Covers: AC-6 (wrong), EC-18. One clean query does not hide a second query with a drop term."""
    p = plan("BOTH", S("where are the cambros kept"), S("cambros for 6 gallons"), B(**M1_TOOL))
    assert "search" in score(cases["M1"], p)


def test_drop_checked_per_query_not_joined(score, cases):
    """Covers: AC-6 (boundary), EC-18. Drop terms are checked per query: '1' and '6' in two queries do not make '16'."""
    p = plan("BOTH", S("where are the cambros 1"), S("cambros kept 6x"), B(**M1_TOOL))
    assert score(cases["M1"], p) == set()


def test_keep_match_is_case_insensitive(score, cases):
    """Covers: AC-6 (right), EC-18. Query text is casefolded before the keep check."""
    assert score(cases["D2"], plan("DOCS", S("SHOULD I BRING LEMONS FOR THE ICED TEA"))) == set()


def test_d3_placement_passes_through_plac(score, cases):
    """Covers: AC-6 (right), EC-18. D3 query '5 gallon cambros placement' passes (LOC term 'plac')."""
    assert score(cases["D3"], plan("DOCS", S("5 gallon cambros placement"))) == set()


def test_d3_without_location_or_go_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. D3 query '5 gallon cambros' has no LOC/go term and fails search."""
    assert "search" in score(cases["D3"], plan("DOCS", S("5 gallon cambros")))


def test_d10_no_syrups_passes(score, cases):
    """Covers: AC-6 (right), EC-18. D10 query 'What if there are no syrups?' passes ('no syrup')."""
    assert score(cases["D10"], plan("DOCS", S("What if there are no syrups?"))) == set()


def test_d10_without_syrup_fails(score, cases):
    """Covers: AC-6 (wrong), EC-18. D10 query lacking 'syrup' fails search."""
    assert "search" in score(cases["D10"], plan("DOCS", S("what if there is nothing there backup")))


def test_loc_group_includes_plac(cases):
    """Covers: AC-6 (right), EC-18. LOC gained 'plac' and D10 gained 'no syrup' in the case table."""
    assert "plac" in cases["M1"]["keep"][1]
    assert "no syrup" in cases["D10"]["keep"][1]
    assert "not found" in cases["D10"]["keep"][1]
    assert "not there" in cases["D10"]["keep"][1]


def test_docs_case_has_no_drop_terms(score, cases):
    """Covers: AC-6 (right), EC-18. D3 keeps '5' as a keep term; an amount in the query is fine."""
    assert cases["D3"]["drop"] == []
    assert score(cases["D3"], plan("DOCS", S("where do the 5 gallon cambros go"))) == set()


def test_d1_needs_both_drinks(score, cases):
    """Covers: AC-6 (wrong), EC-18. D1 with only 'coffee' in the query lacks the 'hot water' group."""
    assert "search" in score(cases["D1"], plan("DOCS", S("what supplies do I need for coffee")))


# --------------------------------------------------------------------------
# Case table sanity and NFR-4
# --------------------------------------------------------------------------

def test_thirty_cases_ten_per_path(cases):
    """Covers: AC-7/AC-8/AC-9 (right), extra. The case table has T1-T10, D1-D10, M1-M10."""
    expected = {f"{p}{i}" for p in "TDM" for i in range(1, 11)}
    assert set(cases) == expected
    assert all(cases[k]["route"] == {"T": "TOOL", "D": "DOCS", "M": "BOTH"}[k[0]] for k in cases)


def test_prompt_and_search_description_hold_no_eval_question(cases):
    """Covers: NFR-4 (wrong). No eval question appears word for word in the prompt or the search description."""
    for text in (PLANNER_PROMPT, SEARCH_TOOL.description):
        folded = text.casefold()
        for c in cases.values():
            assert c["question"].casefold() not in folded, c["id"]

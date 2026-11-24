"""Spec 045 section 6.1 SCOPE (AC-1 to AC-6, AC-8): the always tool by scope. Unit, no model, no file."""
from __future__ import annotations

import pytest

from blc.tools.always_tools import (
    ALWAYS_CHECK_ITEMS,
    ALWAYS_COUNT_ITEMS,
    ALWAYS_DRIP_TRAY_ITEMS,
    ALWAYS_SCOPES,
    ALWAYS_TABLE_ITEMS,
    ALWAYS_STATUSES,
    calculate_always_items,
)

T4 = {"black linens": 9, "purple napkins": 8}
D3 = {"black napkins": 3}
BOTH_2_3 = {"black linens": 5, "black napkins": 3, "purple napkins": 4}
ZERO_TABLES = {"black linens": 0, "purple napkins": 0}


def test_scope_constants():
    """Covers: AC-1 (right), section 3.1. The scope constants have the specified values."""
    assert ALWAYS_SCOPES == ("tables", "drip_trays", "both")
    assert ALWAYS_TABLE_ITEMS == ("black linens", "purple napkins")
    assert ALWAYS_DRIP_TRAY_ITEMS == ("black napkins",)


# ---------------------------------------------------------------- SCOPE-1 to SCOPE-4 (AC-1)

def test_scope_1_tables_only_ok(run_tool):
    """Covers: AC-1 (right), SCOPE-1. about tables, tables 4: linens and purple napkins only."""
    r = run_tool({"about": "tables", "tables": 4})
    assert r.status == "ok"
    assert r.counts == T4


def test_scope_2_drip_trays_only_ok(run_tool):
    """Covers: AC-1 (right), SCOPE-2. about drip_trays, drip_trays 3: black napkins only."""
    r = run_tool({"about": "drip_trays", "drip_trays": 3})
    assert r.status == "ok"
    assert r.counts == D3


def test_scope_3_both_ok(run_tool):
    """Covers: AC-1 (right), SCOPE-3. about both, tables 2, drip_trays 3: the spec 044 CALC-1 counts."""
    r = run_tool({"about": "both", "tables": 2, "drip_trays": 3})
    assert r.status == "ok"
    assert r.counts == BOTH_2_3


def test_scope_4_tables_zero(run_tool):
    """Covers: AC-1 (boundary), SCOPE-4. about tables, tables 0: ok with zero counts (0 linens, not 1)."""
    r = run_tool({"about": "tables", "tables": 0})
    assert r.status == "ok"
    assert r.counts == ZERO_TABLES


def test_scope_drip_trays_zero(run_tool):
    """Covers: AC-1 (boundary). Extra: about drip_trays, drip_trays 0 is ok with a zero napkin count."""
    r = run_tool({"about": "drip_trays", "drip_trays": 0})
    assert r.status == "ok"
    assert r.counts == {"black napkins": 0}


@pytest.mark.parametrize("tables,linens,purple", [(1, 3, 2), (5, 11, 10), (6, 13, 12)])
def test_tables_scope_formula(run_tool, tables, linens, purple):
    """Covers: AC-1 (right). Extra: spec 044 formulas hold under the tables scope."""
    r = run_tool({"about": "tables", "tables": tables})
    assert r.counts == {"black linens": linens, "purple napkins": purple}


# ---------------------------------------------------------------- SCOPE-5, SCOPE-6 (AC-2)

@pytest.mark.parametrize("args", [
    {"about": "tables", "drip_trays": 3},
    {"about": "drip_trays", "tables": 4},
])
def test_scope_5_missing_in_scope_number_needs_info(run_tool, args):
    """Covers: AC-2 (wrong), SCOPE-5. The in-scope number is missing (the out-of-scope one is given):
    need_info with no counts."""
    r = run_tool(args)
    assert r.status == "need_info"
    assert r.counts == {}


@pytest.mark.parametrize("args", [
    {"about": "tables"},
    {"about": "tables", "tables": None},
    {"about": "tables", "tables": ""},
    {"about": "drip_trays", "drip_trays": "  "},
])
def test_missing_in_scope_blank_forms(run_tool, args):
    """Covers: AC-2 (boundary). Extra: missing, null and blank in-scope values all mean not given."""
    r = run_tool(args)
    assert r.status == "need_info"
    assert r.counts == {}


@pytest.mark.parametrize("args,counts", [
    ({"about": "both", "tables": 4}, T4),
    ({"about": "both", "drip_trays": 3}, D3),
    ({"about": "both"}, {}),
])
def test_scope_6_both_partial(run_tool, args, counts):
    """Covers: AC-2 (wrong), SCOPE-6. about both with one or no number: need_info with the known counts."""
    r = run_tool(args)
    assert r.status == "need_info"
    assert r.counts == counts


def test_both_partial_with_null_values(run_tool):
    """Covers: AC-2 (boundary). Extra: explicit nulls for both numbers under both give need_info with {}."""
    r = run_tool({"about": "both", "tables": None, "drip_trays": None})
    assert (r.status, r.counts) == ("need_info", {})


def test_missing_out_of_scope_never_asks(run_tool):
    """Covers: AC-2 (right). A missing out-of-scope number never causes need_info."""
    assert run_tool({"about": "tables", "tables": 4}).status == "ok"
    assert run_tool({"about": "drip_trays", "drip_trays": 3}).status == "ok"
    assert run_tool({"about": "tables", "tables": 4, "drip_trays": None}).status == "ok"


# ---------------------------------------------------------------- SCOPE-7 (AC-3)

SCOPE_7_ARGS = [
    {"about": "tables", "tables": 4},
    {"about": "drip_trays", "drip_trays": 3},
    {"about": "both", "tables": 2, "drip_trays": 3},
    {"about": "tables", "tables": 0},
    {"about": "tables", "drip_trays": 3},
    {"about": "drip_trays", "tables": 4},
    {"about": "both", "tables": 4},
    {"about": "both", "drip_trays": 3},
    {"about": "both"},
]


@pytest.mark.parametrize("args", SCOPE_7_ARGS)
def test_scope_7_checks_and_count_order(run_tool, args):
    """Covers: AC-3 (right), SCOPE-7. checks is ("bus tubs", "towels") on ok and need_info; counts keys follow
    ALWAYS_COUNT_ITEMS order."""
    r = run_tool(args)
    assert r.status in ("ok", "need_info")
    assert r.checks == ("bus tubs", "towels") == ALWAYS_CHECK_ITEMS
    assert r.counts is not None
    order = [ALWAYS_COUNT_ITEMS.index(k) for k in r.counts]
    assert order == sorted(order)
    assert set(r.counts) <= set(ALWAYS_COUNT_ITEMS)


@pytest.mark.parametrize("args", [
    {"about": "tables", "tables": -1},
    {"about": "both", "tables": "two"},
    None,
])
def test_checks_and_counts_none_only_on_invalid(run_tool, args):
    """Covers: AC-3 (wrong). checks and counts are None on invalid."""
    r = run_tool(args)
    assert r.status == "invalid"
    assert r.checks is None and r.counts is None


def test_status_always_allowed(run_tool):
    """Covers: AC-3 (boundary). Every outcome uses a status from ALWAYS_STATUSES."""
    for args in SCOPE_7_ARGS + [None, {"tables": -1}]:
        assert run_tool(args).status in ALWAYS_STATUSES


# ---------------------------------------------------------------- SCOPE-8, SCOPE-9 (AC-4)

@pytest.mark.parametrize("about,expected", [
    ("TABLES", "tables"),
    (" drip trays ", "drip_trays"),
    ("Both", "both"),
    ("drip_trays", "drip_trays"),
    ("  Tables  ", "tables"),
    ("DRIP TRAYS", "drip_trays"),
    ("Drip_Trays", "drip_trays"),
])
def test_scope_8_about_normalised(run_tool, about, expected):
    """Covers: AC-4 (right), SCOPE-8. Case and spaces are ignored; "drip trays" means drip_trays. Checked by
    giving only one number: the scope decides whether that is ok or need_info."""
    tables_only = run_tool({"about": about, "tables": 4})
    trays_only = run_tool({"about": about, "drip_trays": 3})
    if expected == "tables":
        assert (tables_only.status, tables_only.counts) == ("ok", T4)
        assert (trays_only.status, trays_only.counts) == ("need_info", {})
    elif expected == "drip_trays":
        assert (tables_only.status, tables_only.counts) == ("need_info", {})
        assert (trays_only.status, trays_only.counts) == ("ok", D3)
    else:
        assert (tables_only.status, tables_only.counts) == ("need_info", T4)
        assert (trays_only.status, trays_only.counts) == ("need_info", D3)


@pytest.mark.parametrize("about", ["MISSING", None, "", "   ", "linens", 3, True, ["tables"], {"a": 1}])
def test_scope_9_unknown_about_is_both(run_tool, about):
    """Covers: AC-4 (wrong), SCOPE-9. Missing, null, blank, unknown or non-string about is treated as both: ok
    with all three counts, never invalid."""
    args = {"tables": 2, "drip_trays": 3}
    if about != "MISSING":
        args["about"] = about
    r = run_tool(args)
    assert r.status == "ok"
    assert r.counts == BOTH_2_3


def test_unknown_about_with_one_number_is_both_need_info(run_tool):
    """Covers: AC-4 (boundary). Extra: an unknown about with only tables behaves as both (asks drip trays)."""
    r = run_tool({"about": "linens", "tables": 4})
    assert (r.status, r.counts) == ("need_info", T4)


# ---------------------------------------------------------------- SCOPE-10 to SCOPE-12 (AC-5)

@pytest.mark.parametrize("bad", ["two", -1, 2.5, True, [1], {"n": 1}])
def test_scope_10_out_of_scope_ignored_tables(run_tool, bad):
    """Covers: AC-5 (right), SCOPE-10. about tables: any drip_trays value, even invalid, has no effect."""
    r = run_tool({"about": "tables", "tables": 4, "drip_trays": bad})
    assert r.status == "ok"
    assert r.counts == T4


@pytest.mark.parametrize("bad", ["two", -1, 2.5, False])
def test_out_of_scope_ignored_drip_trays(run_tool, bad):
    """Covers: AC-5 (right), SCOPE-10. The same the other way round: about drip_trays ignores tables."""
    r = run_tool({"about": "drip_trays", "drip_trays": 3, "tables": bad})
    assert r.status == "ok"
    assert r.counts == D3


def test_out_of_scope_invalid_with_in_scope_missing_is_need_info(run_tool):
    """Covers: AC-5 (boundary). An invalid out-of-scope value does not make the call invalid, and the missing
    in-scope number still gives need_info."""
    r = run_tool({"about": "tables", "drip_trays": -1})
    assert (r.status, r.counts) == ("need_info", {})


@pytest.mark.parametrize("bad", ["two", -1, 2.5])
def test_scope_11_in_scope_invalid(run_tool, bad):
    """Covers: AC-5 (wrong), SCOPE-11. about tables with a bad tables value is invalid; checks and counts None."""
    r = run_tool({"about": "tables", "tables": bad})
    assert r.status == "invalid"
    assert r.checks is None and r.counts is None


@pytest.mark.parametrize("bad", [True, [2], {"n": 2}, "-1", "2.5"])
def test_in_scope_invalid_other_forms(run_tool, bad):
    """Covers: AC-5 (wrong). Extra: boolean, list, dict and string forms are invalid for the in-scope value."""
    assert run_tool({"about": "tables", "tables": bad}).status == "invalid"
    assert run_tool({"about": "drip_trays", "drip_trays": bad}).status == "invalid"


@pytest.mark.parametrize("value", [2, 2.0, "2", " 2 "])
def test_in_scope_accepted_forms(run_tool, value):
    """Covers: AC-5 (right). The spec 044 forms 2, 2.0, "2" and " 2 " mean the same under a scope."""
    r = run_tool({"about": "tables", "tables": value})
    assert (r.status, r.counts) == ("ok", {"black linens": 5, "purple napkins": 4})


def test_scope_12_invalid_beats_need_info(run_tool):
    """Covers: AC-5 (boundary), SCOPE-12. about both, tables "two", drip_trays missing: invalid, not
    need_info."""
    assert run_tool({"about": "both", "tables": "two"}).status == "invalid"
    assert run_tool({"about": "both", "drip_trays": -1}).status == "invalid"


@pytest.mark.parametrize("args", [[], [2, 3], "tables=2", None, 5, ["tables"]])
def test_non_mapping_args_invalid(run_tool, args):
    """Covers: AC-5 (wrong). A non-mapping args is invalid and nothing raises."""
    r = run_tool(args)
    assert r.status == "invalid"
    assert r.checks is None and r.counts is None


def test_unknown_keys_ignored(run_tool):
    """Covers: AC-5 (right). Unknown keys are ignored."""
    r = run_tool({"about": "tables", "tables": 4, "guests": 70})
    assert (r.status, r.counts) == ("ok", T4)


# ---------------------------------------------------------------- SCOPE-13 (AC-6)

def test_scope_13_direct_matches_run(run_tool):
    """Covers: AC-6 (right), SCOPE-13. calculate_always_items gives the same results as run_always_tool."""
    assert calculate_always_items(4, None, "tables") == run_tool({"about": "tables", "tables": 4})
    assert calculate_always_items(None, None, "drip_trays") == run_tool({"about": "drip_trays"})
    assert calculate_always_items(None, 3, "both") == run_tool({"about": "both", "drip_trays": 3})
    assert calculate_always_items(2, 3, "drip trays") == run_tool({"about": "drip trays", "tables": 2,
                                                                  "drip_trays": 3})


def test_scope_13_default_about_is_both(run_tool):
    """Covers: AC-6 (right), SCOPE-13. (2, 3) with no about is the spec 044 CALC-1 result."""
    r = calculate_always_items(2, 3)
    assert (r.status, r.counts) == ("ok", BOTH_2_3)
    assert r == calculate_always_items(2, 3, "both")
    assert calculate_always_items(4, None) == calculate_always_items(4, None, "both")


def test_scope_13_direct_drip_trays_need_info():
    """Covers: AC-6 (wrong), SCOPE-13. (None, None, "drip_trays") is need_info with no counts."""
    r = calculate_always_items(None, None, "drip_trays")
    assert (r.status, r.counts, r.checks) == ("need_info", {}, ALWAYS_CHECK_ITEMS)


def test_direct_negative_in_scope_invalid_and_out_of_scope_ignored():
    """Covers: AC-6 (wrong), AC-5 (boundary). Negative in-scope is invalid; negative out-of-scope is ignored."""
    assert calculate_always_items(-1, None, "tables").status == "invalid"
    assert calculate_always_items(4, -1, "tables").status == "ok"
    assert calculate_always_items(-1, 3, "drip_trays").status == "ok"
    assert calculate_always_items(2, -1, "both").status == "invalid"


@pytest.mark.parametrize("about", ["nonsense", "", None, 7])
def test_direct_bad_about_is_both(about):
    """Covers: AC-6 (boundary), AC-4. A bad about given directly behaves as both and never raises."""
    r = calculate_always_items(2, 3, about)
    assert (r.status, r.counts) == ("ok", BOTH_2_3)

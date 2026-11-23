"""Spec 044 section 6.1 CALC: counts and calculate_always_items."""
import pytest

from blc.tools.always_tools import (
    ALWAYS_CHECK_ITEMS,
    ALWAYS_COUNT_ITEMS,
    calculate_always_items,
)


def test_calc_1_two_tables_three_trays(expected_calc_1):
    """Covers: AC-1 (right), CALC-1. tables 2, drip_trays 3."""
    r = calculate_always_items(2, 3)
    assert r.status == "ok"
    assert r.counts == expected_calc_1


@pytest.mark.parametrize(
    "tables,linens,purple",
    [(1, 3, 2), (3, 7, 6), (10, 21, 20)],
)
def test_calc_2_formula(tables, linens, purple):
    """Covers: AC-1 (right/boundary), CALC-2. Linens 2t+1, purple 2t, napkins = trays."""
    r = calculate_always_items(tables, 1)
    assert r.status == "ok"
    assert r.counts == {
        "black linens": linens,
        "black napkins": 1,
        "purple napkins": purple,
    }


def test_calc_3_all_zero():
    """Covers: AC-2 (boundary), CALC-3. 0 tables and 0 trays is ok with zero counts."""
    r = calculate_always_items(0, 0)
    assert r.status == "ok"
    assert r.counts == {"black linens": 0, "black napkins": 0, "purple napkins": 0}
    assert r.checks == ALWAYS_CHECK_ITEMS


def test_calc_4_zero_tables_not_one_linen():
    """Covers: AC-2 (boundary), CALC-4. tables 0 gives 0 linens (not 1)."""
    r = calculate_always_items(0, 2)
    assert r.status == "ok"
    assert r.counts == {"black linens": 0, "black napkins": 2, "purple napkins": 0}


def test_calc_5_zero_trays():
    """Covers: AC-1 (right), AC-2 (boundary), CALC-5. drip_trays 0 gives 0 napkins."""
    r = calculate_always_items(4, 0)
    assert r.status == "ok"
    assert r.counts == {"black linens": 9, "black napkins": 0, "purple napkins": 8}


@pytest.mark.parametrize("tables,trays", [(2, 3), (0, 0), (1, 0), (5, 5)])
def test_calc_6_checks_and_key_order(tables, trays):
    """Covers: AC-1 (right), CALC-6. checks fixed; counts keys in ALWAYS_COUNT_ITEMS order."""
    r = calculate_always_items(tables, trays)
    assert r.status == "ok"
    assert r.checks == ("bus tubs", "towels")
    assert r.checks == ALWAYS_CHECK_ITEMS
    assert list(r.counts) == list(ALWAYS_COUNT_ITEMS)


def test_calc_7_direct_ok(expected_calc_1):
    """Covers: AC-6 (right), CALC-7. Direct call (2, 3) is ok."""
    r = calculate_always_items(2, 3)
    assert (r.status, r.counts) == ("ok", expected_calc_1)


def test_calc_7_direct_need_info():
    """Covers: AC-6 (wrong), AC-3, CALC-7. None means not given."""
    r = calculate_always_items(None, 3)
    assert r.status == "need_info"
    assert r.checks is None
    assert r.counts is None


def test_calc_7_direct_invalid_negative():
    """Covers: AC-6 (wrong), AC-4, CALC-7. Negative tables is invalid, no exception."""
    r = calculate_always_items(-1, 3)
    assert r.status == "invalid"
    assert r.checks is None
    assert r.counts is None


def test_direct_negative_drip_trays_invalid():
    """Covers: AC-6 (wrong), AC-4. Extra: negative drip_trays is invalid."""
    assert calculate_always_items(2, -1).status == "invalid"


def test_direct_both_none_need_info():
    """Covers: AC-6 (wrong), AC-3. Extra: both None is need_info."""
    r = calculate_always_items(None, None)
    assert r.status == "need_info"
    assert r.counts is None


def test_direct_invalid_beats_need_info():
    """Covers: AC-4 (boundary), AC-6. Extra: negative plus None is invalid."""
    assert calculate_always_items(-1, None).status == "invalid"
    assert calculate_always_items(None, -1).status == "invalid"


def test_direct_matches_run_always_tool(run):
    """Covers: AC-6 (right). Same values give the same result through both entry points."""
    for tables, trays in [(2, 3), (0, 0), (None, 3), (2, None), (-1, 3), (None, None)]:
        args = {}
        if tables is not None:
            args["tables"] = tables
        if trays is not None:
            args["drip_trays"] = trays
        assert calculate_always_items(tables, trays) == run(args)

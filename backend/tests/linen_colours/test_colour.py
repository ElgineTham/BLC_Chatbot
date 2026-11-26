"""Spec 047 section 6.1 COLOUR (AC-1 to AC-4): white linens in the always tool. Unit, no model, no file."""
from __future__ import annotations

import pytest

from blc.tools.always_tools import (
    ALWAYS_COUNT_ITEMS,
    ALWAYS_COUNT_ORDER,
    ALWAYS_WHITE_LINENS,
    calculate_always_items,
    run_always_tool,
)

W5 = {"white linens": 11, "purple napkins": 10}
B3_W2 = {"black linens": 7, "white linens": 5, "purple napkins": 10}


def _question(text):
    return text.strip().splitlines()[-1]


# ---------------------------------------------------------------- COLOUR-10 constants

def test_colour_10_constants():
    """Covers: AC-1 (right), COLOUR-10. New constants have the specified values; ALWAYS_COUNT_ITEMS is unchanged."""
    assert ALWAYS_WHITE_LINENS == "white linens"
    assert ALWAYS_COUNT_ORDER == ("black linens", "white linens", "black napkins", "purple napkins")
    assert ALWAYS_COUNT_ITEMS == ("black linens", "black napkins", "purple napkins")


# ---------------------------------------------------------------- COLOUR-1 to COLOUR-4 (AC-1)

def test_colour_1_white_only(run_tool):
    """Covers: AC-1 (right), COLOUR-1. about tables, white_tables 5: white linens 11 and purple napkins 10 only."""
    r = run_tool({"about": "tables", "white_tables": 5})
    assert r.status == "ok"
    assert r.counts == W5
    assert list(r.counts) == ["white linens", "purple napkins"]


def test_colour_2_black_and_white_in_order(run_tool):
    """Covers: AC-1 (right), COLOUR-2. tables 3 and white_tables 2: counts in ALWAYS_COUNT_ORDER."""
    r = run_tool({"about": "tables", "tables": 3, "white_tables": 2})
    assert r.status == "ok"
    assert r.counts == B3_W2
    assert list(r.counts) == ["black linens", "white linens", "purple napkins"]


def test_colour_2_order_independent_of_argument_order(run_tool):
    """Covers: AC-1 (boundary), COLOUR-2. Key order in the args dict does not change the counts order."""
    r = run_tool({"white_tables": 2, "tables": 3, "about": "tables"})
    assert list(r.counts) == ["black linens", "white linens", "purple napkins"]


def test_colour_3_black_zero_white_two(run_tool):
    """Covers: AC-1 (boundary), COLOUR-3. tables 0 and white_tables 2: black linens 0 (not 1), white 5, purple 4."""
    r = run_tool({"about": "tables", "tables": 0, "white_tables": 2})
    assert r.status == "ok"
    assert r.counts == {"black linens": 0, "white linens": 5, "purple napkins": 4}
    assert list(r.counts) == ["black linens", "white linens", "purple napkins"]


def test_colour_3_white_zero_only(run_tool):
    """Covers: AC-1 (boundary), COLOUR-3. white_tables 0 alone: white linens 0 (not 1), purple napkins 0."""
    r = run_tool({"about": "tables", "white_tables": 0})
    assert r.status == "ok"
    assert r.counts == {"white linens": 0, "purple napkins": 0}


def test_white_one_table(run_tool):
    """Covers: AC-1 (boundary). Extra: white_tables 1 gives 3 white linens and 2 purple napkins."""
    r = run_tool({"about": "tables", "white_tables": 1})
    assert r.counts == {"white linens": 3, "purple napkins": 2}


@pytest.mark.parametrize("n,linens,purple", [(1, 3, 2), (2, 5, 4), (5, 11, 10), (6, 13, 12)])
def test_white_formula(run_tool, n, linens, purple):
    """Covers: AC-1 (right). Extra: white linens are n x 2 + 1 and purple napkins n x 2 for white-only calls."""
    r = run_tool({"about": "tables", "white_tables": n})
    assert r.counts == {"white linens": linens, "purple napkins": purple}


def test_purple_counts_both_colours(run_tool):
    """Covers: AC-1 (right). Extra: purple napkins are (tables + white_tables) x 2 when both are given."""
    r = run_tool({"about": "tables", "tables": 10, "white_tables": 4})
    assert r.counts == {"black linens": 21, "white linens": 9, "purple napkins": 28}


def test_black_only_unchanged(run_tool):
    """Covers: AC-1 (right). Black-only results are identical to spec 045: no white linens key."""
    r = run_tool({"about": "tables", "tables": 4})
    assert r.counts == {"black linens": 9, "purple napkins": 8}
    assert "white linens" not in r.counts


def test_colour_4_both_scope_with_white(run_tool):
    """Covers: AC-1 (right), COLOUR-4. about both, white_tables 5, drip_trays 3: counts in ALWAYS_COUNT_ORDER."""
    r = run_tool({"about": "both", "white_tables": 5, "drip_trays": 3})
    assert r.status == "ok"
    assert r.counts == {"white linens": 11, "black napkins": 3, "purple napkins": 10}
    assert list(r.counts) == ["white linens", "black napkins", "purple napkins"]


def test_both_scope_all_three_numbers(run_tool):
    """Covers: AC-1 (right). Extra: about both with tables, white_tables and drip_trays: all four keys in order."""
    r = run_tool({"about": "both", "tables": 3, "white_tables": 2, "drip_trays": 3})
    assert r.status == "ok"
    assert list(r.counts) == list(ALWAYS_COUNT_ORDER)
    assert r.counts == {"black linens": 7, "white linens": 5, "black napkins": 3, "purple napkins": 10}


# ---------------------------------------------------------------- COLOUR-5, COLOUR-6 (AC-2)

def test_colour_5_both_scope_asks_drip_trays_not_tables(run_tool):
    """Covers: AC-2 (wrong), COLOUR-5. about both, white_tables 5, no drip_trays: need_info with the table counts;
    the question asks drip trays and never tables."""
    r = run_tool({"about": "both", "white_tables": 5})
    assert r.status == "need_info"
    assert r.counts == W5
    q = _question(r.text).lower()
    assert r.text.strip().endswith("?")
    assert "drip trays" in q
    assert "tables" not in q


def test_colour_5_black_only_still_never_asks_tables(run_tool):
    """Covers: AC-2 (right), COLOUR-5. Extra: with tables given and white_tables missing, it never asks for
    white tables or tables."""
    r = run_tool({"about": "both", "tables": 4})
    assert r.status == "need_info"
    assert r.counts == {"black linens": 9, "purple napkins": 8}
    assert "tables" not in _question(r.text).lower()


def test_colour_6_neither_asks_tables(run_tool):
    """Covers: AC-2 (wrong), COLOUR-6. about tables with neither number: need_info asking how many tables."""
    r = run_tool({"about": "tables"})
    assert r.status == "need_info"
    assert r.counts == {}
    q = _question(r.text).lower()
    assert "how many" in q and "tables" in q


def test_colour_6_drip_trays_scope_ignores_white_tables(run_tool):
    """Covers: AC-2 (right), COLOUR-6. about drip_trays, drip_trays 3 with white_tables 5: ok, black napkins only."""
    r = run_tool({"about": "drip_trays", "drip_trays": 3, "white_tables": 5})
    assert r.status == "ok"
    assert r.counts == {"black napkins": 3}


def test_drip_trays_scope_white_tables_alone_still_needs_trays(run_tool):
    """Covers: AC-2 (wrong). Extra: about drip_trays with only white_tables: the in-scope number is missing, so
    need_info with no counts."""
    r = run_tool({"about": "drip_trays", "white_tables": 5})
    assert r.status == "need_info"
    assert r.counts == {}


def test_drip_trays_scope_invalid_white_tables_ignored(run_tool):
    """Covers: AC-2 (boundary), AC-3. Extra: an invalid white_tables is ignored in scope drip_trays."""
    r = run_tool({"about": "drip_trays", "drip_trays": 3, "white_tables": "five"})
    assert r.status == "ok"
    assert r.counts == {"black napkins": 3}


# ---------------------------------------------------------------- COLOUR-7 (AC-3)

@pytest.mark.parametrize("value", ["5", " 5 ", 5.0, 5])
def test_colour_7_accepted_forms(run_tool, value):
    """Covers: AC-3 (right), COLOUR-7. 5, 5.0, "5" and " 5 " all mean 5 white tables (as COLOUR-1)."""
    r = run_tool({"about": "tables", "white_tables": value})
    assert r.status == "ok"
    assert r.counts == W5


@pytest.mark.parametrize("value", [None, "", "   "])
def test_colour_7_blank_means_not_given(run_tool, value):
    """Covers: AC-3 (wrong), COLOUR-7. null and blank white_tables mean not given: asks tables."""
    r = run_tool({"about": "tables", "white_tables": value})
    assert r.status == "need_info"
    assert r.counts == {}
    assert "tables" in _question(r.text).lower()


def test_colour_7_blank_white_does_not_hide_black(run_tool):
    """Covers: AC-3 (boundary), COLOUR-7. Extra: a blank white_tables with tables 4 is a normal black-only call."""
    r = run_tool({"about": "tables", "tables": 4, "white_tables": None})
    assert r.status == "ok"
    assert r.counts == {"black linens": 9, "purple napkins": 8}


@pytest.mark.parametrize("value", [-1, "five", True, False, 2.5, "2.5", [5], {"n": 5}, "-1"])
def test_colour_7_invalid_values(run_tool, value):
    """Covers: AC-3 (wrong), COLOUR-7. A negative, fraction, non-numeric, boolean, list or dict white_tables is
    invalid and nothing raises."""
    r = run_tool({"about": "tables", "white_tables": value})
    assert r.status == "invalid"
    assert r.counts is None


def test_invalid_white_tables_beats_valid_tables(run_tool):
    """Covers: AC-3 (boundary). Extra: an invalid white_tables makes the call invalid even when tables is fine."""
    r = run_tool({"about": "tables", "tables": 3, "white_tables": -1})
    assert r.status == "invalid"
    assert r.counts is None


def test_invalid_white_tables_in_both_scope(run_tool):
    """Covers: AC-3 (wrong). Extra: invalid white_tables is invalid under about both too."""
    r = run_tool({"about": "both", "white_tables": "five", "drip_trays": 3})
    assert r.status == "invalid"


# ---------------------------------------------------------------- COLOUR-8 (AC-3)

def test_colour_8_function_matches_runner(run_tool):
    """Covers: AC-3 (right), COLOUR-8. calculate_always_items(3, None, "tables", 2) equals the runner's result."""
    direct = calculate_always_items(3, None, "tables", 2)
    via_args = run_always_tool({"about": "tables", "tables": 3, "white_tables": 2})
    assert direct == via_args
    assert direct.counts == B3_W2


@pytest.mark.parametrize("args,kwargs", [
    ({"about": "tables", "white_tables": 5}, dict(tables=None, drip_trays=None, about="tables", white_tables=5)),
    ({"about": "both", "white_tables": 5, "drip_trays": 3}, dict(tables=None, drip_trays=3, about="both", white_tables=5)),
    ({"about": "both", "white_tables": 5}, dict(tables=None, drip_trays=None, about="both", white_tables=5)),
    ({"about": "tables", "white_tables": -1}, dict(tables=None, drip_trays=None, about="tables", white_tables=-1)),
    ({"about": "tables"}, dict(tables=None, drip_trays=None, about="tables", white_tables=None)),
])
def test_colour_8_function_matches_runner_more(args, kwargs):
    """Covers: AC-3 (boundary), COLOUR-8. Extra: the function and the runner agree on ok, need_info and invalid."""
    assert calculate_always_items(**kwargs) == run_always_tool(args)


def test_function_white_tables_defaults_to_not_given():
    """Covers: AC-3 (boundary). Extra: white_tables is optional, so the old four-argument-free call still works."""
    assert calculate_always_items(4, None, "tables") == run_always_tool({"about": "tables", "tables": 4})
    assert calculate_always_items(2, 3) == run_always_tool({"tables": 2, "drip_trays": 3, "about": "both"})


# ---------------------------------------------------------------- COLOUR-9 (AC-4)

def test_colour_9_white_line_shown(run_tool):
    """Covers: AC-4 (right), COLOUR-9. The COLOUR-1 text contains 'White linens: 11' plus bus tubs and towels."""
    text = run_tool({"about": "tables", "white_tables": 5}).text
    assert "White linens: 11" in text
    assert "Purple napkins: 10" in text
    assert "Bus tubs" in text and "Towels" in text
    assert "Black linens" not in text


def test_colour_9_no_white_line_for_black_only(run_tool):
    """Covers: AC-4 (wrong), COLOUR-9. The spec 045 SCOPE-1 text (tables 4) has no 'White linens'."""
    text = run_tool({"about": "tables", "tables": 4}).text
    assert "White linens" not in text
    assert "white linens" not in text.lower()
    assert "Black linens: 9" in text


def test_no_white_line_in_drip_tray_scope(run_tool):
    """Covers: AC-4 (wrong). Extra: no White linens line when the scope is drip_trays, even with white_tables."""
    text = run_tool({"about": "drip_trays", "drip_trays": 3, "white_tables": 5}).text
    assert "white linens" not in text.lower()
    assert "Black napkins: 3" in text


def test_text_white_zero_is_shown(run_tool):
    """Covers: AC-4 (boundary). Extra: white linens 0 is in counts, so 'White linens: 0' is shown."""
    text = run_tool({"about": "tables", "white_tables": 0}).text
    assert "White linens: 0" in text


def test_text_lists_in_count_order(run_tool):
    """Covers: AC-4 (right). The lines follow ALWAYS_COUNT_ORDER: Black linens, White linens, Black napkins,
    Purple napkins."""
    text = run_tool({"about": "both", "tables": 3, "white_tables": 2, "drip_trays": 3}).text
    positions = [text.index(s) for s in ("Black linens: 7", "White linens: 5", "Black napkins: 3", "Purple napkins: 10")]
    assert positions == sorted(positions)


def test_text_need_info_lists_known_white(run_tool):
    """Covers: AC-4 (right). Extra: a need_info text still lists the known white linens."""
    text = run_tool({"about": "both", "white_tables": 5}).text
    assert "White linens: 11" in text and "Purple napkins: 10" in text
    assert "Bus tubs" in text and "Towels" in text

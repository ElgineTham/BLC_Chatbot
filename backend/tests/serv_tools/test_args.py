"""Spec 042 section 6.3 ARGS (AC-4, AC-5, AC-6, AC-7). Unit."""

from __future__ import annotations

import pytest

from blc.tools.serv_tools import SERV_STATUSES, calculate_serving_utensils, run_serv_tool


@pytest.mark.parametrize("food", [
    "BUTTER  croissants",
    "butter-croissants",
    "Butter croissants served with raspberry preserves",
    "  butter croissants  ",
    "butter_croissants",
    "butter, croissants",
    "BUTTER CROISSANTS SERVED WITH RASPBERRY PRESERVES",
])
def test_food_name_matching(run, food):
    """Covers: AC-4 (right), ARGS-1. Case, spaces, punctuation and aliases all match."""
    r = run([{"food": food, "qty": 3}])
    assert r.status == "ok"
    assert r.foods == ("butter croissants",)
    assert r.utensils == {"small tongs": 4}


def test_hyphenated_canonical_matches_without_hyphen(run):
    """Covers: AC-4 (right). 'quinoa chickpea tabbouleh salad' matches 'quinoa-chickpea ...'."""
    r = run([{"food": "Quinoa chickpea tabbouleh salad", "qty": 1}])
    assert r.status == "ok"
    assert r.foods == ("quinoa-chickpea tabbouleh salad",)


def test_alias_with_surrounding_noise(run):
    """Covers: AC-4 (right). Another alias works and resolves to its canonical food."""
    r = run([{"food": "assorted  BAGELS with cream-cheese", "qty": 1}])
    assert r.status == "ok" and r.foods == ("assorted bagels",)


def test_partial_name_is_unknown(run):
    """Covers: AC-4 (wrong). Only whole names/aliases match, not substrings."""
    r = run([{"food": "butter", "qty": 1}])
    assert r.status == "invalid"


@pytest.mark.parametrize("qty", ["3", 3.0, 3])
def test_qty_shapes_equal(run, qty):
    """Covers: AC-7 (right), ARGS-2. '3', 3.0 and 3 are the same qty."""
    r = run([{"food": "butter croissants", "qty": qty}])
    assert r.status == "ok"
    assert r.utensils == {"small tongs": 4}


def test_fractional_qty_accepted(run):
    """Covers: AC-7 (boundary). 1.5 is a valid qty (and 1.5 dozen needs 1 tray -> 2 tongs)."""
    r = run([{"food": "butter croissants", "qty": 1.5}])
    assert r.status == "ok" and r.utensils == {"small tongs": 2}


def test_single_object_as_items(rules):
    """Covers: AC-7 (right), ARGS-3. A lone item object is a one-item list."""
    r = run_serv_tool({"items": {"food": "butter croissants", "qty": 3}}, rules=rules)
    assert r.status == "ok"
    assert r.utensils == {"small tongs": 4}
    assert r.foods == ("butter croissants",)


def test_unknown_keys_ignored(rules):
    """Covers: AC-7 (right), ARGS-4. Extra keys on args and item are ignored."""
    r = run_serv_tool({"items": [{"food": "butter croissants", "qty": 3, "color": "red"}], "color": "red"},
                      rules=rules)
    assert r.status == "ok" and r.utensils == {"small tongs": 4}


@pytest.mark.parametrize("item", [
    {"food": "assorted bagels"},
    {"food": "assorted bagels", "qty": None},
    {"food": "assorted bagels", "qty": 0},
    {"food": "assorted bagels", "qty": 0.0},
    {"food": "assorted bagels", "qty": ""},
    {"food": "assorted bagels", "qty": "  "},
])
def test_missing_null_zero_qty_need_info(run, item):
    """Covers: AC-5 (wrong), ARGS-5. Missing, null, 0 or blank-string qty asks for it; nothing is guessed."""
    r = run([item])
    assert r.status == "need_info"
    assert r.utensils is None and r.foods is None


@pytest.mark.parametrize("food", ["lasagna", "", "   "])
def test_bad_food_invalid(run, food):
    """Covers: AC-6 (wrong), ARGS-6. Unknown or blank food."""
    r = run([{"food": food, "qty": 3}])
    assert r.status == "invalid"
    assert r.utensils is None and r.foods is None


def test_missing_food_invalid(run):
    """Covers: AC-6 (wrong), ARGS-6. A line with no food key."""
    assert run([{"qty": 3}]).status == "invalid"


@pytest.mark.parametrize("food", [None, 5, ["butter croissants"]])
def test_non_string_food_invalid(run, food):
    """Covers: AC-6 (wrong). A non-string food (extra case)."""
    assert run([{"food": food, "qty": 3}]).status == "invalid"


@pytest.mark.parametrize("qty", [-2, "three", -0.5, "-1", [3], {"a": 1}])
def test_bad_qty_invalid(run, qty):
    """Covers: AC-6 (wrong), ARGS-7. Negative or non-numeric qty is invalid."""
    r = run([{"food": "butter croissants", "qty": qty}])
    assert r.status == "invalid"
    assert r.utensils is None


@pytest.mark.parametrize("items_kw", [
    {},
    {"items": []},
    {"items": None},
    {"items": "croissants"},
    {"items": 5},
])
def test_bad_items_invalid(rules, items_kw):
    """Covers: AC-6 (wrong), ARGS-8. items missing, empty, null, a string or a number."""
    r = run_serv_tool(dict(items_kw), rules=rules)
    assert r.status == "invalid"
    assert r.utensils is None and r.foods is None


def test_items_with_non_object_entry_invalid(rules):
    """Covers: AC-6 (wrong). items must be a list of objects (extra case)."""
    assert run_serv_tool({"items": ["butter croissants"]}, rules=rules).status == "invalid"
    assert run_serv_tool({"items": [3]}, rules=rules).status == "invalid"


@pytest.mark.parametrize("args", [["butter croissants"], "butter croissants", None, 5])
def test_args_not_mapping_invalid(rules, args):
    """Covers: AC-6 (wrong), ARGS-9. Non-mapping args give invalid, no exception."""
    r = run_serv_tool(args, rules=rules)
    assert r.status == "invalid"


def test_invalid_beats_need_info(run):
    """Covers: AC-6 (boundary), ARGS-10. A bad line makes the call invalid even if another lacks qty."""
    r = run([{"food": "lasagna", "qty": 3}, {"food": "butter croissants"}])
    assert r.status == "invalid"
    assert r.utensils is None


def test_invalid_beats_need_info_either_order(run):
    """Covers: AC-6 (boundary). Same as above with the lines swapped."""
    r = run([{"food": "butter croissants"}, {"food": "lasagna", "qty": 3}])
    assert r.status == "invalid"


def test_invalid_line_voids_good_lines(run):
    """Covers: AC-6 (boundary). One bad line and one good line: no partial totals."""
    r = run([{"food": "butter croissants", "qty": 3}, {"food": "lasagna", "qty": 3}])
    assert r.status == "invalid"
    assert r.utensils is None and r.foods is None


def test_blank_qty_with_bad_food_is_invalid(run):
    """Covers: AC-5 (boundary), AC-6 (boundary). Blank-string qty is need_info alone, but invalid beats it."""
    assert run([{"food": "assorted bagels", "qty": ""}]).status == "need_info"
    assert run([{"food": "lasagna", "qty": "  "}]).status == "invalid"


def test_need_info_with_good_line(run):
    """Covers: AC-5 (right), ARGS-11. Good line plus a line with no qty: need_info, no totals."""
    r = run([{"food": "butter croissants", "qty": 3}, {"food": "assorted bagels"}])
    assert r.status == "need_info"
    assert r.utensils is None and r.foods is None


def test_statuses_are_from_serv_statuses(run):
    """Covers: AC-6 (right). Every status seen is one of SERV_STATUSES."""
    results = [
        run([{"food": "butter croissants", "qty": 1}]),
        run([{"food": "butter croissants"}]),
        run([{"food": "nope", "qty": 1}]),
    ]
    assert [r.status for r in results] == ["ok", "need_info", "invalid"]
    assert all(r.status in SERV_STATUSES for r in results)


def test_direct_call_missing_qty_need_info(rules):
    """Covers: AC-5 (wrong). calculate_serving_utensils with qty None or 0 is need_info."""
    assert calculate_serving_utensils([("assorted bagels", None, None)], rules=rules).status == "need_info"
    assert calculate_serving_utensils([("assorted bagels", 0, None)], rules=rules).status == "need_info"


def test_direct_call_bad_input_invalid_not_raised(rules):
    """Covers: AC-6 (wrong). Direct calls with a bad food or negative qty return invalid."""
    assert calculate_serving_utensils([("lasagna", 1, None)], rules=rules).status == "invalid"
    assert calculate_serving_utensils([("assorted bagels", -1, None)], rules=rules).status == "invalid"
    assert calculate_serving_utensils([("", 1, None)], rules=rules).status == "invalid"

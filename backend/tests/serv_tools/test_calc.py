"""Spec 042 section 6.1 CALC (AC-1, AC-2). Unit."""

from __future__ import annotations

import pytest

from blc.tools.serv_tools import SERV_UTENSILS, ServResult, calculate_serving_utensils


def calc(rules, lines):
    return calculate_serving_utensils(lines, rules=rules)


def test_croissants_three_dozen(rules):
    """Covers: AC-1 (right), CALC-1. 3 dozen -> ceil(1.5)=2 trays x 2 tongs = 4."""
    r = calc(rules, [("butter croissants", 3, None)])
    assert isinstance(r, ServResult)
    assert r.status == "ok"
    assert r.utensils == {"small tongs": 4}
    assert r.foods == ("butter croissants",)


@pytest.mark.parametrize("qty,mayo", [(25, 1), (26, 2), (50, 2), (51, 3)])
def test_deli_sandwich_thresholds(rules, qty, mayo):
    """Covers: AC-1 (boundary), CALC-2. mayo/mustard steps at every 25; large tongs stay 1."""
    r = calc(rules, [("classic deli sandwiches", qty, None)])
    assert r.status == "ok"
    assert r.utensils == {"large tongs": 1, "mayo/mustard": mayo}


def test_two_foods_add_up(rules):
    """Covers: AC-1 (right), CALC-3. Same utensil from two foods adds."""
    r = calc(rules, [("butter croissants", 2, None), ("assorted bagels", 2, None)])
    assert r.utensils == {"small tongs": 3, "spreader/knives": 1}
    assert r.foods == ("butter croissants", "assorted bagels")


def test_repeated_food_counted_separately(rules):
    """Covers: AC-1 (boundary), CALC-4. Two 1-dozen lines are 2 trays, not 1 tray of 2 dozen (which would be 2)."""
    r = calc(rules, [("butter croissants", 1, None), ("butter croissants", 1, None)])
    assert r.utensils == {"small tongs": 4}
    assert r.foods == ("butter croissants", "butter croissants")


def test_count_with_per_one(rules):
    """Covers: AC-1 (right), CALC-5. tabbouleh 3 -> 3 salad tongs and 3 bowls."""
    r = calc(rules, [("quinoa-chickpea tabbouleh salad", 3, None)])
    assert r.utensils == {"salad tongs": 3, "dressing/sauce bowl": 3}


def test_key_order_follows_serv_utensils(rules):
    """Covers: AC-1 (right), CALC-6. Keys follow SERV_UTENSILS order whatever the input order."""
    r = calc(rules, [
        ("yogurt with toppings", 10, None),
        ("tabbouleh salad", 1, None),
        ("deli sandwiches", 10, None),
        ("butter croissants", 1, None),
    ])
    assert r.status == "ok"
    keys = list(r.utensils)
    assert keys == ["small tongs", "large tongs", "salad tongs", "dressing/sauce bowl",
                    "serving spoon", "mayo/mustard", "honey bear"]
    assert keys == sorted(keys, key=SERV_UTENSILS.index)


def test_no_utensil_food_only(rules):
    """Covers: AC-2 (right), CALC-7. A known food that needs nothing gives ok with {}."""
    r = calc(rules, [("trail mix", 12, None)])
    assert r.status == "ok"
    assert r.utensils == {}
    assert r.foods == ("trail mix",)


def test_no_utensil_food_plus_other(rules):
    """Covers: AC-1 (right), AC-2 (right), CALC-8. The empty food adds nothing; no zero keys."""
    r = calc(rules, [("trail mix", 12, None), ("butter croissants", 1, None)])
    assert r.utensils == {"small tongs": 2}
    assert r.foods == ("trail mix", "butter croissants")


def test_repeated_utensil_in_one_food_adds_up(rules):
    """Covers: AC-1 (right), CALC-10. yogurt 68: two spoon entries of 2 -> 4; honey bear 2."""
    r = calc(rules, [("yogurt with toppings", 68, None)])
    assert r.utensils == {"serving spoon": 4, "honey bear": 2}


@pytest.mark.parametrize("dozens,tongs", [(0.5, 2), (2, 2), (2.5, 4), (4, 4), (4.5, 6)])
def test_tray_boundaries(rules, dozens, tongs):
    """Covers: AC-1 (boundary), CALC-9. Tray = 2 dozen; any part of a tray needs its tongs."""
    r = calc(rules, [("butter croissants", dozens, None)])
    assert r.status == "ok"
    assert r.utensils == {"small tongs": tongs}


def test_only_positive_totals_in_utensils(rules):
    """Covers: AC-1 (right). Utensils with total 0 are not listed."""
    r = calc(rules, [("assorted bagels", 1, None)])
    assert all(v > 0 for v in r.utensils.values())
    assert "large tongs" not in r.utensils


def test_foods_use_canonical_names_in_input_order(rules):
    """Covers: AC-1 (right), AC-4 (right). foods holds canonical names (not the alias typed) in input order."""
    r = calc(rules, [("tabbouleh salad", 1, None), ("bagels", 1, None), ("deli sandwiches", 5, None)])
    assert r.foods == ("quinoa-chickpea tabbouleh salad", "assorted bagels", "classic deli sandwiches")


def test_ok_result_has_text(rules):
    """Covers: AC-1 (right). An ok result carries a non-empty text."""
    r = calc(rules, [("butter croissants", 1, None)])
    assert isinstance(r.text, str) and r.text.strip()

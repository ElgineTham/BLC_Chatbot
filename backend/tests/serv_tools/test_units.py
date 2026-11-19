"""Spec 042 section 6.2 UNIT (AC-3, AC-6). Unit."""

from __future__ import annotations

import pytest

from blc.tools.serv_tools import SERV_UNITS, calculate_serving_utensils


def test_unit_constants():
    """Covers: AC-3 (right). SERV_UNITS is as in the interface contract."""
    assert SERV_UNITS == ("each", "dozen", "bags", "packages")


@pytest.mark.parametrize("qty,tongs", [(70, 6), (24, 2), (25, 4)])
def test_each_converts_to_dozen(rules, qty, tongs):
    """Covers: AC-3 (boundary), UNIT-1. 70 each = 5.83 dozen -> 6; 24 each = 2 dozen -> 2; 25 each -> 4."""
    r = calculate_serving_utensils([("butter croissants", qty, "each")], rules=rules)
    assert r.status == "ok"
    assert r.utensils == {"small tongs": tongs}


def test_dozen_converts_to_each(rules):
    """Covers: AC-3 (right), UNIT-2. Deli sandwiches 2 dozen = 24 each -> mayo/mustard 1."""
    r = calculate_serving_utensils([("classic deli sandwiches", 2, "dozen")], rules=rules)
    assert r.status == "ok"
    assert r.utensils == {"large tongs": 1, "mayo/mustard": 1}


def test_dozen_to_each_boundary(rules):
    """Covers: AC-3 (boundary). 3 dozen = 36 each -> mayo/mustard 2 (not 1)."""
    r = calculate_serving_utensils([("classic deli sandwiches", 3, "dozen")], rules=rules)
    assert r.utensils["mayo/mustard"] == 2


@pytest.mark.parametrize("unit", ["Dozen", "dz", "dozens", "DOZEN", " dozen ", "DZ"])
def test_dozen_spellings(rules, unit):
    """Covers: AC-3 (right), UNIT-3. Spellings of dozen are accepted and give the same answer."""
    r = calculate_serving_utensils([("butter croissants", 3, unit)], rules=rules)
    assert r.status == "ok"
    assert r.utensils == {"small tongs": 4}


@pytest.mark.parametrize("unit", ["bag", "Bags", " BAG "])
def test_bag_spellings(rules, unit):
    """Covers: AC-3 (right). bag/Bags accepted for a bags food."""
    r = calculate_serving_utensils([("trail mix", 12, unit)], rules=rules)
    assert r.status == "ok" and r.utensils == {}


@pytest.mark.parametrize("unit", ["Each", "EACH"])
def test_each_spelling(rules, unit):
    """Covers: AC-3 (right). 'each' is matched ignoring case."""
    r = calculate_serving_utensils([("classic deli sandwiches", 25, unit)], rules=rules)
    assert r.status == "ok"


def test_own_unit_given_explicitly(rules):
    """Covers: AC-3 (right). Giving the food's own unit equals giving none."""
    a = calculate_serving_utensils([("butter croissants", 3, "dozen")], rules=rules)
    b = calculate_serving_utensils([("butter croissants", 3, None)], rules=rules)
    assert a.utensils == b.utensils


def test_unit_none_uses_food_unit(rules):
    """Covers: AC-3 (right). No unit: deli qty 51 is in 'each'."""
    r = calculate_serving_utensils([("classic deli sandwiches", 51, None)], rules=rules)
    assert r.utensils["mayo/mustard"] == 3


def test_bags_for_dozen_food_invalid(rules):
    """Covers: AC-3 (wrong), AC-6 (wrong), UNIT-4. bags vs dozen is a mismatch."""
    r = calculate_serving_utensils([("butter croissants", 3, "bags")], rules=rules)
    assert r.status == "invalid"
    assert r.utensils is None and r.foods is None


def test_package_for_dozen_food_invalid(rules):
    """Covers: AC-3 (wrong). packages vs dozen is a mismatch."""
    r = calculate_serving_utensils([("butter croissants", 3, "packages")], rules=rules)
    assert r.status == "invalid"


@pytest.mark.parametrize("unit", ["each", "dozen"])
def test_each_or_dozen_for_bags_food_invalid(rules, unit):
    """Covers: AC-3 (wrong). each/dozen do not convert to bags."""
    r = calculate_serving_utensils([("trail mix", 12, unit)], rules=rules)
    assert r.status == "invalid"


def test_pounds_invalid(rules):
    """Covers: AC-6 (wrong), UNIT-5. An unknown unit is invalid."""
    r = calculate_serving_utensils([("butter croissants", 3, "pounds")], rules=rules)
    assert r.status == "invalid"
    assert r.utensils is None


def test_unit_via_raw_args(rules):
    """Covers: AC-3 (right). The raw 'unit' key is honoured: 70 each -> 6 tongs."""
    from blc.tools.serv_tools import run_serv_tool
    r = run_serv_tool({"items": [{"food": "butter croissants", "qty": 70, "unit": "each"}]}, rules=rules)
    assert r.status == "ok" and r.utensils == {"small tongs": 6}


def test_unit_null_in_raw_args(rules):
    """Covers: AC-3 (boundary). unit null in raw args means the food's unit."""
    from blc.tools.serv_tools import run_serv_tool
    r = run_serv_tool({"items": [{"food": "butter croissants", "qty": 3, "unit": None}]}, rules=rules)
    assert r.status == "ok" and r.utensils == {"small tongs": 4}

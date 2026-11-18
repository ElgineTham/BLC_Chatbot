"""Spec 029 section 6.1 COUNT (AC-1, AC-2, AC-5, AC-6, AC-7 for count items). Unit."""

from __future__ import annotations

import pytest

from blc.tools.food_tools import FoodResult, calculate_food_item

COUNT_ITEMS = ("spoons", "forks", "knives", "small plates", "large plates")

BOUNDARIES = [(1, 10, 11), (20, 10, 30), (21, 20, 41), (50, 20, 70),
              (51, 50, 101), (100, 50, 150), (101, 100, 201), (150, 100, 250)]


@pytest.mark.parametrize("guests,extra,count", BOUNDARIES[:4])
def test_lower_tier_boundaries(rules, guests, extra, count):
    """Covers: AC-1 (boundary), COUNT-1. Tiers up to 50 guests."""
    r = calculate_food_item("forks", guests=guests, rules=rules)
    assert r.status == "ok"
    assert (r.extra, r.count) == (extra, count)


@pytest.mark.parametrize("guests,extra,count", BOUNDARIES[4:])
def test_upper_tier_boundaries(rules, guests, extra, count):
    """Covers: AC-1 (boundary), COUNT-2. Tiers above 50 guests, including the open last tier."""
    r = calculate_food_item("forks", guests=guests, rules=rules)
    assert r.status == "ok"
    assert (r.extra, r.count) == (extra, count)


def test_fields_for_forks_70(rules):
    """Covers: AC-1 (right), COUNT-3. Every field of a count result."""
    r = calculate_food_item("forks", guests=70, rules=rules)
    assert isinstance(r, FoodResult)
    assert r.status == "ok"
    assert r.item == "forks"
    assert r.guests == 70
    assert r.extra == 50
    assert r.count == 120
    assert r.answer is None
    assert r.meal is None


@pytest.mark.parametrize("item", COUNT_ITEMS)
def test_all_count_items_same_numbers(rules, item):
    """Covers: AC-1 (right), AC-2 (right), COUNT-4. Each of the five items gives 120 for 70 guests."""
    r = calculate_food_item(item, guests=70, rules=rules)
    assert r.status == "ok"
    assert r.item == item
    assert (r.guests, r.extra, r.count) == (70, 50, 120)


@pytest.mark.parametrize("guests", [1, 20, 21, 70, 101, 500])
def test_items_agree_with_each_other(rules, guests):
    """Covers: AC-2 (right). For the same guests all five items give identical numbers."""
    seen = {calculate_food_item(i, guests=guests, rules=rules).count for i in COUNT_ITEMS}
    assert len(seen) == 1


@pytest.mark.parametrize("guests", [None, 0])
def test_no_guests_is_need_info(rules, guests):
    """Covers: AC-5 (wrong), COUNT-5. None or 0 guests asks for more info; nothing is guessed."""
    r = calculate_food_item("spoons", guests=guests, rules=rules)
    assert r.status == "need_info"
    assert r.count is None and r.extra is None and r.guests is None
    assert r.item == "spoons"


def test_guests_omitted_is_need_info(rules):
    """Covers: AC-5 (wrong), COUNT-5. Leaving guests out entirely."""
    r = calculate_food_item("spoons", rules=rules)
    assert r.status == "need_info"
    assert r.count is None


def test_negative_guests_invalid(rules):
    """Covers: AC-6 (wrong), COUNT-6. -5 guests is invalid, no exception."""
    r = calculate_food_item("knives", guests=-5, rules=rules)
    assert r.status == "invalid"
    assert r.count is None


def test_unknown_meal_ignored_for_count_item(rules):
    """Covers: AC-7 (right), COUNT-7. A bad meal does not make a count item invalid."""
    r = calculate_food_item("forks", guests=70, meal="brunch", rules=rules)
    assert r.status == "ok"
    assert r.count == 120
    assert r.meal is None


def test_unknown_item_invalid(rules):
    """Covers: AC-6 (wrong). An item not in FOOD_ITEMS is invalid."""
    r = calculate_food_item("chairs", guests=10, rules=rules)
    assert r.status == "invalid"
    assert r.item is None


def test_invalid_beats_need_info(rules):
    """Covers: AC-6 (boundary). Unknown item with no guests is invalid, not need_info."""
    assert calculate_food_item("chairs", rules=rules).status == "invalid"

"""Spec 029 section 6.3 ARGS (AC-4, AC-5, AC-6, AC-7, AC-8) through run_food_tool. Unit."""

from __future__ import annotations

import pytest

from blc.tools.food_tools import run_food_tool


@pytest.mark.parametrize("raw,canon", [
    ("Fork", "forks"), ("SMALL  plate", "small plates"), ("small_plates", "small plates"),
    ("large-plates", "large plates"), ("  Spoon ", "spoons"), ("knife", "knives"),
    ("FORKS", "forks"), ("large plate", "large plates"),
])
def test_count_item_name_forms(rules, raw, canon):
    """Covers: AC-4 (right), ARGS-1. Item names ignore case, spaces, _ and -, and accept singular."""
    r = run_food_tool({"item": raw, "guests": 70}, rules)
    assert r.status == "ok"
    assert r.item == canon
    assert r.count == 120


@pytest.mark.parametrize("raw,canon", [
    ("Cocktail Napkin", "cocktail napkins"), ("dinner_napkin", "dinner napkins"),
    ("Dinner-Napkins", "dinner napkins"),
])
def test_napkin_item_name_forms(rules, raw, canon):
    """Covers: AC-4 (right), ARGS-1. Napkin item name forms."""
    r = run_food_tool({"item": raw, "meal": "lunch"}, rules)
    assert r.status == "ok"
    assert r.item == canon
    assert r.answer is not None


@pytest.mark.parametrize("guests", ["70", 70.0, 70])
def test_guests_shapes(rules, guests):
    """Covers: AC-8 (right), ARGS-2. '70', 70.0 and 70 are the same guests."""
    r = run_food_tool({"item": "forks", "guests": guests}, rules)
    assert r.status == "ok"
    assert (r.guests, r.count) == (70, 120)


def test_one_item_lists(rules):
    """Covers: AC-8 (right), ARGS-3. A one-item list for item or meal is that item."""
    a = run_food_tool({"item": ["forks"], "guests": 70}, rules)
    b = run_food_tool({"item": "dinner napkins", "meal": ["lunch"]}, rules)
    assert a.status == "ok" and a.count == 120 and a.item == "forks"
    assert b.status == "ok" and b.answer is True and b.meal == "lunch"


@pytest.mark.parametrize("args", [
    {"guests": 70}, {"item": None, "guests": 70}, {"item": "", "guests": 70},
    {"item": "   ", "guests": 70}, {"item": "chairs", "guests": 70},
])
def test_bad_item_invalid(rules, args):
    """Covers: AC-6 (wrong), ARGS-4. Missing, null, blank or unknown item is invalid."""
    r = run_food_tool(args, rules)
    assert r.status == "invalid"
    assert r.item is None


def test_two_items_invalid(rules):
    """Covers: AC-6 (wrong), ARGS-5. A list of two items is invalid."""
    assert run_food_tool({"item": ["forks", "knives"], "guests": 70}, rules).status == "invalid"


def test_empty_item_list_invalid(rules):
    """Covers: AC-6 (boundary). An empty list is not exactly one item."""
    assert run_food_tool({"item": [], "guests": 70}, rules).status == "invalid"


@pytest.mark.parametrize("guests", ["seventy", -5, 2.5, "2.5", "-5"])
def test_bad_guests_invalid(rules, guests):
    """Covers: AC-6 (wrong), ARGS-6, COUNT-6. Non-whole or negative guests for a count item."""
    r = run_food_tool({"item": "forks", "guests": guests}, rules)
    assert r.status == "invalid"
    assert r.count is None


@pytest.mark.parametrize("args", [["item", "forks"], "forks", None, 5])
def test_args_not_mapping_invalid(rules, args):
    """Covers: AC-6 (wrong), ARGS-7. Non-mapping args are invalid, no exception."""
    assert run_food_tool(args, rules).status == "invalid"


def test_extra_keys_ignored(rules):
    """Covers: AC-7 (right), ARGS-8. Unknown keys are ignored."""
    r = run_food_tool({"item": "forks", "guests": 70, "color": "red"}, rules)
    assert r.status == "ok" and r.count == 120


def test_invalid_item_beats_invalid_guests_and_need_info(rules):
    """Covers: AC-6 (boundary), ARGS-9. Unknown item with bad guests is invalid."""
    assert run_food_tool({"item": "chairs", "guests": -5}, rules).status == "invalid"
    assert run_food_tool({"item": "chairs"}, rules).status == "invalid"


def test_invalid_guests_beats_need_info_for_meal(rules):
    """Covers: AC-6 (boundary). Bad guests on a count item is invalid even with a stray bad meal."""
    assert run_food_tool({"item": "forks", "guests": "seventy", "meal": "brunch"}, rules).status == "invalid"


def test_item_only_is_need_info(rules):
    """Covers: AC-5 (wrong), ARGS-10. A count item with no guests."""
    assert run_food_tool({"item": "forks"}, rules).status == "need_info"


@pytest.mark.parametrize("guests", [None, 0])
def test_null_or_zero_guests_need_info(rules, guests):
    """Covers: AC-5 (boundary). null and 0 guests mean not given."""
    r = run_food_tool({"item": "forks", "guests": guests}, rules)
    assert r.status == "need_info"
    assert r.count is None


@pytest.mark.parametrize("args", [
    {"item": "dinner napkins"}, {"item": "dinner napkins", "meal": None},
    {"item": "dinner napkins", "meal": "  "}, {"item": "dinner napkins", "meal": ""},
])
def test_napkin_without_meal_need_info(rules, args):
    """Covers: AC-5 (wrong). No, null or blank meal."""
    r = run_food_tool(args, rules)
    assert r.status == "need_info"
    assert r.answer is None


def test_napkin_unknown_meal_invalid(rules):
    """Covers: AC-6 (wrong). A meal not in the rules."""
    assert run_food_tool({"item": "dinner napkins", "meal": "brunch"}, rules).status == "invalid"


def test_napkin_two_meals_invalid(rules):
    """Covers: AC-6 (wrong), AC-8. A list of two meals is not exactly one string."""
    assert run_food_tool({"item": "dinner napkins", "meal": ["lunch", "dinner"]}, rules).status == "invalid"


def test_guests_ignored_for_napkins_even_if_bad(rules):
    """Covers: AC-7 (right). Bad guests on a napkin item are ignored."""
    for g in ("seventy", -5, 2.5):
        r = run_food_tool({"item": "cocktail napkins", "meal": "lunch", "guests": g}, rules)
        assert r.status == "ok" and r.answer is False


def test_meal_ignored_for_count_even_if_bad(rules):
    """Covers: AC-7 (right). Unknown or list meals on a count item are ignored."""
    for m in ("brunch", ["a", "b"]):
        r = run_food_tool({"item": "forks", "guests": 70, "meal": m}, rules)
        assert r.status == "ok" and r.count == 120


def test_empty_mapping_invalid(rules):
    """Covers: AC-6 (boundary). An empty dict has no item."""
    assert run_food_tool({}, rules).status == "invalid"

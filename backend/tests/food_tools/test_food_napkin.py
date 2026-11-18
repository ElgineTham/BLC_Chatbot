"""Spec 029 section 6.2 NAPKIN (AC-3, AC-4, AC-5, AC-6, AC-7 for napkin items). Unit."""

from __future__ import annotations

import pytest

from blc.tools.food_tools import calculate_food_item

MEALS = ("breakfast", "reception", "lunch", "dinner")


@pytest.mark.parametrize("meal,expected", zip(MEALS, [True, True, False, False]))
def test_cocktail_napkins(rules, meal, expected):
    """Covers: AC-3 (right), NAPKIN-1. Cocktail napkins by meal."""
    r = calculate_food_item("cocktail napkins", meal=meal, rules=rules)
    assert r.status == "ok"
    assert r.answer is expected
    assert r.item == "cocktail napkins"
    assert r.meal == meal


@pytest.mark.parametrize("meal,expected", zip(MEALS, [False, False, True, True]))
def test_dinner_napkins(rules, meal, expected):
    """Covers: AC-3 (right), NAPKIN-2. Dinner napkins by meal."""
    r = calculate_food_item("dinner napkins", meal=meal, rules=rules)
    assert r.status == "ok"
    assert r.answer is expected
    assert r.item == "dinner napkins"


@pytest.mark.parametrize("raw,canon", [("Lunch", "lunch"), (" DINNER ", "dinner"), ("lunch", "lunch")])
def test_meal_case_and_spaces(rules, raw, canon):
    """Covers: AC-4 (right), NAPKIN-3. Meal names ignore case and surrounding spaces; meal is canonical."""
    r = calculate_food_item("dinner napkins", meal=raw, rules=rules)
    assert r.status == "ok"
    assert r.answer is True
    assert r.meal == canon


@pytest.mark.parametrize("meal", [None, "  ", ""])
def test_no_meal_is_need_info(rules, meal):
    """Covers: AC-5 (wrong), NAPKIN-4. No, None or blank meal asks for more info."""
    r = calculate_food_item("dinner napkins", meal=meal, rules=rules)
    assert r.status == "need_info"
    assert r.answer is None


def test_meal_omitted_is_need_info(rules):
    """Covers: AC-5 (wrong), NAPKIN-4. Meal left out."""
    r = calculate_food_item("cocktail napkins", rules=rules)
    assert r.status == "need_info"
    assert r.answer is None


def test_unknown_meal_invalid(rules):
    """Covers: AC-6 (wrong), NAPKIN-5. 'brunch' is not in the rules, so invalid (not guessed)."""
    r = calculate_food_item("dinner napkins", meal="brunch", rules=rules)
    assert r.status == "invalid"
    assert r.answer is None


def test_guests_ignored_for_napkins(rules):
    """Covers: AC-7 (right), NAPKIN-6. Bad guests never make a napkin item invalid."""
    r = calculate_food_item("cocktail napkins", guests=-5, meal="lunch", rules=rules)
    assert r.status == "ok"
    assert r.answer is False


def test_napkin_result_fields(rules):
    """Covers: AC-3 (right), NAPKIN-7. guests/extra/count are None and answer is a real bool."""
    r = calculate_food_item("dinner napkins", guests=70, meal="lunch", rules=rules)
    assert r.guests is None and r.extra is None and r.count is None
    assert isinstance(r.answer, bool)


def test_no_meal_with_unknown_item_is_invalid(rules):
    """Covers: AC-6 (boundary), precedence. Unknown item beats a missing meal."""
    assert calculate_food_item("napkins", rules=rules).status == "invalid"

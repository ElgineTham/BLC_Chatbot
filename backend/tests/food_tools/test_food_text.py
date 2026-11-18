"""Spec 029 section 6.4 TEXT (AC-9). Unit."""

from __future__ import annotations

import re

import pytest

from blc.tools.food_tools import FOOD_ITEMS, calculate_food_item, run_food_tool


def _word(text, w):
    return re.search(rf"\b{w}\b", text) is not None


def test_ok_count_text(rules):
    """Covers: AC-9 (right), TEXT-1. Name, count, guests and extra appear."""
    t = calculate_food_item("forks", guests=70, rules=rules).text
    for part in ("Forks", "120", "70 guests", "50 extra"):
        assert part in t


def test_ok_count_text_other_item(rules):
    """Covers: AC-9 (right). The item name in the text follows the item."""
    t = calculate_food_item("small plates", guests=1, rules=rules).text
    assert "Small plates" in t and "11" in t and "10 extra" in t


def test_ok_napkin_yes(rules):
    """Covers: AC-9 (right), TEXT-2. Whole word yes, and not no."""
    t = calculate_food_item("dinner napkins", meal="lunch", rules=rules).text
    assert "Dinner napkins" in t and "lunch" in t
    assert _word(t, "yes") and not _word(t, "no")


def test_ok_napkin_no(rules):
    """Covers: AC-9 (right), TEXT-3. Whole word no, and not yes."""
    t = calculate_food_item("cocktail napkins", meal="lunch", rules=rules).text
    assert _word(t, "no") and not _word(t, "yes")


def test_need_info_count_text(rules):
    """Covers: AC-9 (wrong), TEXT-4. One question mentioning guests."""
    t = calculate_food_item("forks", rules=rules).text.strip()
    assert t.endswith("?")
    assert "guests" in t


def test_need_info_napkin_text(rules):
    """Covers: AC-9 (wrong), TEXT-5. One question mentioning meal and every meal in the rules."""
    t = calculate_food_item("dinner napkins", rules=rules).text.strip()
    assert t.endswith("?")
    assert "meal" in t
    for m in ("breakfast", "reception", "lunch", "dinner"):
        assert m in t


def test_need_info_lists_rules_meals(rules, write_rules, appendix_a):
    """Covers: AC-9 (boundary). Meal names come from the rules file, not a fixed list."""
    from blc.tools.food_tools import load_food_rules
    appendix_a["napkins"]["brunch"] = {"cocktail": True, "dinner": False}
    r2 = load_food_rules(write_rules(appendix_a, "food2.json"))
    assert "brunch" in calculate_food_item("dinner napkins", rules=r2).text


def test_invalid_unknown_item_text(rules):
    """Covers: AC-9 (wrong), TEXT-6. Starts with invalid, has the three quoted keys and all items."""
    t = calculate_food_item("chairs", guests=5, rules=rules).text
    assert t.lower().startswith("invalid")
    for k in ('"item"', '"guests"', '"meal"'):
        assert k in t
    for name in FOOD_ITEMS:
        assert name in t


def test_invalid_guests_text(rules):
    """Covers: AC-9 (wrong), TEXT-7. Bad guests text has the format hint."""
    t = calculate_food_item("forks", guests=-5, rules=rules).text
    assert t.lower().startswith("invalid")
    for k in ('"item"', '"guests"', '"meal"'):
        assert k in t


@pytest.mark.parametrize("args", [
    {"item": "dinner napkins", "meal": "brunch"}, ["x"], None, {}, {"item": ["forks", "knives"]},
    {"item": "forks", "guests": "seventy"},
])
def test_every_invalid_text_has_format(rules, args):
    """Covers: AC-9 (wrong). Every invalid text starts with invalid and contains the three quoted keys."""
    r = run_food_tool(args, rules)
    assert r.status == "invalid"
    assert r.text.lower().startswith("invalid")
    for k in ('"item"', '"guests"', '"meal"'):
        assert k in r.text

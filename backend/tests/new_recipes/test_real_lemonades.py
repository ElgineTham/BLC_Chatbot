"""Spec 040 AC-1, AC-2, AC-5, AC-11: real recipes.json, lemonades and names (REAL-1..5, 17..19). Skips without the file."""

from __future__ import annotations

import json
from fractions import Fraction as Fr

import pytest

from blc.tools.recipe_tools import RECIPES_FILE, scale_recipe

NINE = [
    "Lemonade", "Strawberry Lemonade", "Pomegranate Lemonade", "Lavender Lemonade", "Mango Lemonade",
    "Mango Iced Tea", "Raspberry Iced Tea", "Citrus Fruit Punch", "Apple Cider with Ginger",
]


def _ing(r):
    return [(i.name, i.amount, i.unit, i.fill) for i in r.ingredients]


def test_real_file_has_exactly_nine_recipes(real_book):
    """Covers: AC-1 (right), REAL-18. The real file holds exactly the nine display names."""
    with open(RECIPES_FILE, encoding="utf-8") as f:
        names = list(json.load(f)["recipes"])
    assert sorted(names) == sorted(NINE)


@pytest.mark.parametrize("name", NINE)
def test_each_recipe_scales_ok(real_book, name):
    """Covers: AC-1 (right). Every display name finds its own recipe at 1 gallon."""
    r = scale_recipe(name, gallons=1, book=real_book)
    assert r.status == "ok" and r.recipe == name and r.steps


@pytest.mark.parametrize("name,syrup_name,syrup_1gal", [
    ("Strawberry Lemonade", "Strawberry syrup", 7),
    ("Lavender Lemonade", "Lavender syrup", 7),
    ("Mango Lemonade", "Mango syrup", 7),
    ("Pomegranate Lemonade", "Pomegranate juice", 8),
])
@pytest.mark.parametrize("gallons", [1, 4])
def test_lemonades_scale_linearly(real_book, name, syrup_name, syrup_1gal, gallons):
    """Covers: AC-2 (right), REAL-1, REAL-2, REAL-3. 25 oz concentrate, syrup/juice, Water fill; linear (4 gal is 4x, not the card's 3x)."""
    r = scale_recipe(name, gallons=gallons, book=real_book)
    assert r.status == "ok"
    assert _ing(r) == [
        ("Lemonade concentrate", Fr(25 * gallons), "oz", False),
        (syrup_name, Fr(syrup_1gal * gallons), "oz", False),
        ("Water", Fr(gallons), "gallon", True),
    ]


def test_strawberry_4_gallons_not_card_values(real_book):
    """Covers: AC-2 (wrong), REAL-2. 4 gallons gives 100 and 28 oz, not the card's 75 and 20."""
    r = scale_recipe("strawberry lemonade", gallons=4, book=real_book)
    amounts = [i.amount for i in r.ingredients if not i.fill]
    assert amounts == [100, 28]
    assert 75 not in amounts and 20 not in amounts


def test_pomegranate_4_gallons(real_book):
    """Covers: AC-2 (right), REAL-3. 100 oz concentrate and 32 oz Pomegranate juice."""
    r = scale_recipe("Pomegranate Lemonade", gallons=4, book=real_book)
    assert [i.amount for i in r.ingredients] == [100, 32, 4]


def test_lavender_fractional_batch(real_book):
    """Covers: AC-2 (boundary), REAL-4. 2.5 gallons is exact fractions and text numbers."""
    r = scale_recipe("Lavender Lemonade", gallons=2.5, book=real_book)
    assert r.ingredients[0].amount == Fr(125, 2)
    assert r.ingredients[1].amount == Fr(35, 2)
    assert "62.5 oz" in r.text and "17.5 oz" in r.text and "2.5 gallons" in r.text


def test_mango_lemonade_by_guests(real_book):
    """Covers: AC-2 (right), AC-8, REAL-5. 100 guests is 4 gallons, from_guests True."""
    r = scale_recipe("Mango Lemonade", guests=100, book=real_book)
    assert r.status == "ok" and r.gallons == 4 and r.from_guests is True
    assert r.ingredients[0].amount == 100 and r.ingredients[1].amount == 28


def test_lemonade_steps_present(real_book):
    """Covers: AC-2 (right). Steps are returned and numbered in the text."""
    r = scale_recipe("Mango Lemonade", gallons=1, book=real_book)
    assert len(r.steps) >= 1
    assert "1." in r.text


def test_old_lemonade_unchanged(real_book):
    """Covers: AC-1 (right), AC-11, REAL-19. Lemonade at 6 gallons is still 42 oz Lemon concentrate."""
    r = scale_recipe("Lemonade", gallons=6, book=real_book)
    assert _ing(r) == [("Lemon concentrate", Fr(42), "oz", False), ("Water", Fr(6), "gallon", True)]


@pytest.mark.parametrize("name,display", [
    ("STRAWBERRY LEMONADE recipe", "Strawberry Lemonade"),
    ("the mango tea", "Mango Iced Tea"),
    ("Raspberry tea", "Raspberry Iced Tea"),
    ("citrus punch", "Citrus Fruit Punch"),
    ("fruit punch", "Citrus Fruit Punch"),
    ("Punch", "Citrus Fruit Punch"),
    ("ginger apple cider", "Apple Cider with Ginger"),
    ("apple cider", "Apple Cider with Ginger"),
    ("Fresh-pressed WA apple cider with ginger", "Apple Cider with Ginger"),
    ("ginger cider", "Apple Cider with Ginger"),
    ("  pomegranate   lemonade ", "Pomegranate Lemonade"),
    ("The Lavender Lemonade Recipe", "Lavender Lemonade"),
    ("mango iced tea", "Mango Iced Tea"),
    ("raspberry iced tea", "Raspberry Iced Tea"),
    ("citrus fruit punch", "Citrus Fruit Punch"),
    ("apple cider with ginger", "Apple Cider with Ginger"),
    ("mango lemonade", "Mango Lemonade"),
])
def test_names_and_aliases_find_recipes(real_book, name, display):
    """Covers: AC-5 (right), REAL-17. Display names and aliases (case, spacing, "the", "recipe") find their recipe."""
    r = scale_recipe(name, gallons=2, book=real_book)
    assert r.status == "ok"
    assert r.recipe == display


@pytest.mark.parametrize("name", ["raspberry lemonade", "mango", "lemon", "tea", "iced tea", "cider", "strawberry"])
def test_unknown_and_partial_names_no_recipe(real_book, name):
    """Covers: AC-5 (wrong), AC-1, REAL-18. Drinks without a card and partial names give no_recipe listing all nine names."""
    r = scale_recipe(name, gallons=2, book=real_book)
    assert r.status == "no_recipe"
    assert r.recipe is None and r.ingredients == ()
    for display in NINE:
        assert display in r.text
    assert "no recipe" in r.text.lower()


def test_no_recipe_precedence_over_need_info(real_book):
    """Covers: AC-5 (boundary). An unknown name with no amounts is no_recipe, not need_info."""
    assert scale_recipe("mango", book=real_book).status == "no_recipe"

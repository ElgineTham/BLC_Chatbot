"""Spec 015 AC-2: scale_recipe results (EC-3 to EC-10). Unit; no model, no network."""

from __future__ import annotations

from fractions import Fraction

import pytest

from blc.tools.recipe_tools import RECIPE_STATUSES, RecipeResult, ScaledIngredient, scale_recipe

F = Fraction


def test_statuses_constant():
    """Covers: AC-2 (right). The four statuses, in order."""
    assert RECIPE_STATUSES == ("ok", "need_info", "no_recipe", "invalid")


def test_lemonade_six_gallons(book, ing, lemonade_steps):
    """Covers: AC-2 (right), EC-3. Lemonade for 6 gallons: exact result."""
    r = scale_recipe("lemonade", gallons=6, book=book)
    assert isinstance(r, RecipeResult)
    assert r.status == "ok"
    assert r.recipe == "Lemonade"
    assert r.gallons == 6
    assert r.from_guests is False
    assert ing(r) == [("Lemon concentrate", 42, "oz", False), ("Water", 6, "gallon", True)]
    assert all(isinstance(i, ScaledIngredient) for i in r.ingredients)
    assert all(isinstance(i.amount, Fraction) for i in r.ingredients)
    assert list(r.steps) == lemonade_steps
    assert isinstance(r.text, str) and r.text


@pytest.mark.parametrize("gallons,oz", [
    (1, F(7)),
    (2.5, F(35, 2)),
    (F(1, 3), F(7, 3)),
    (0.25, F(7, 4)),
])
def test_lemonade_gallon_sizes(book, gallons, oz):
    """Covers: AC-2 (right/boundary), EC-4. Exact fractions; a float is its decimal value."""
    r = scale_recipe("lemonade", gallons=gallons, book=book)
    assert r.status == "ok"
    assert r.ingredients[0].amount == oz
    assert r.ingredients[0].unit == "oz"
    assert r.ingredients[1].amount == r.gallons
    assert r.ingredients[1].unit == "gallon" and r.ingredients[1].fill is True


def test_float_decimal_value_exact(book):
    """Covers: AC-2 (boundary), EC-4. 2.5 gallons is exactly 5/2 (0.1 is exactly 1/10, not binary)."""
    assert scale_recipe("lemonade", gallons=2.5, book=book).gallons == F(5, 2)
    assert scale_recipe("lemonade", gallons=0.1, book=book).gallons == F(1, 10)


@pytest.mark.parametrize("guests,gallons,oz", [
    (1, 1, 7), (25, 1, 7), (37, 1, 7), (38, 2, 14), (70, 3, 21), (75, 3, 21), (120, 5, 35),
])
def test_lemonade_by_guests(book, guests, gallons, oz):
    """Covers: AC-2 (right/boundary), EC-5. 25 guests per gallon, a half rounds up, minimum 1."""
    r = scale_recipe("lemonade", guests=guests, book=book)
    assert r.status == "ok"
    assert r.gallons == gallons
    assert r.ingredients[0].amount == oz
    assert r.from_guests is True


def test_gallons_wins_over_guests(book):
    """Covers: AC-2 (right), EC-6. gallons 4 and guests 120: gallons 4, 28 oz, not from guests."""
    r = scale_recipe("lemonade", gallons=4, guests=120, book=book)
    assert r.status == "ok"
    assert r.gallons == 4
    assert r.ingredients[0].amount == 28
    assert r.from_guests is False


def test_fruit_punch_three_gallons(book, ing):
    """Covers: AC-2 (right), EC-7, NFR-3. Yield 2 recipe scaled to 3 gallons."""
    r = scale_recipe("fruit punch", gallons=3, book=book)
    assert r.status == "ok" and r.recipe == "Fruit punch"
    assert ing(r) == [
        ("Orange concentrate", 15, "oz", False),
        ("Simple syrup", F(9, 2), "oz", False),
        ("Water", 3, "gallon", True),
    ]
    assert len(r.steps) == 2


def test_fruit_punch_one_gallon(book):
    """Covers: AC-2 (right), EC-7. Gallons below the yield: 5 oz and 3/2 oz."""
    r = scale_recipe("fruit punch", gallons=1, book=book)
    assert [i.amount for i in r.ingredients] == [5, F(3, 2), 1]


def test_fruit_punch_by_guests_same_as_three_gallons(book, ing):
    """Covers: AC-2 (right), EC-7. 70 guests is 3 gallons: same ingredients as gallons 3."""
    by_guests = scale_recipe("fruit punch", guests=70, book=book)
    by_gallons = scale_recipe("fruit punch", gallons=3, book=book)
    assert by_guests.gallons == 3 and by_guests.from_guests is True
    assert ing(by_guests) == ing(by_gallons)


@pytest.mark.parametrize("name", ["Lemonade", " lemonade ", "LEMONADE", "lemonade recipe", "the lemonade",
                                  "Fresh  lemonade", "fresh lemonade", "The Lemonade Recipe",
                                  "  the   fresh lemonade   recipe  "])
def test_name_finds_lemonade(book, name):
    """Covers: AC-2 (right), EC-8. Case, spaces, leading 'the', trailing 'recipe' are ignored."""
    r = scale_recipe(name, gallons=1, book=book)
    assert r.status == "ok" and r.recipe == "Lemonade"


def test_name_finds_punch_by_also_written_as(book):
    """Covers: AC-2 (right), EC-8. 'punch' is an also_written_as name of Fruit punch."""
    r = scale_recipe("punch", gallons=2, book=book)
    assert r.status == "ok" and r.recipe == "Fruit punch"


@pytest.mark.parametrize("name", ["lemon", "lemonades", "iced tea", "lemonade recipes", "lemon ade"])
def test_name_no_partial_match(book, name):
    """Covers: AC-2 (wrong), EC-8. No partial matches: no_recipe, no recipe, no ingredients."""
    r = scale_recipe(name, gallons=2, book=book)
    assert r.status == "no_recipe"
    assert r.recipe is None
    assert r.ingredients == () and r.steps == ()
    assert r.gallons is None


def test_need_info(book):
    """Covers: AC-2 (wrong), EC-9. Lemonade with no amounts: need_info with the recipe name found."""
    r = scale_recipe("lemonade", book=book)
    assert r.status == "need_info"
    assert r.recipe == "Lemonade"
    assert r.gallons is None
    assert r.ingredients == () and r.steps == ()


def test_no_recipe_beats_need_info(book):
    """Covers: AC-2 (wrong), EC-9. Unknown recipe with no amounts is no_recipe."""
    assert scale_recipe("iced tea", book=book).status == "no_recipe"


@pytest.mark.parametrize("kwargs", [
    {"gallons": 0}, {"gallons": -2}, {"guests": 0}, {"guests": -5}, {"guests": 2.5},
    {"gallons": F(-1, 2)},
])
def test_invalid_amounts(book, kwargs):
    """Covers: AC-2 (wrong), EC-10 (boundary). Bad amounts give invalid, never raise."""
    r = scale_recipe("lemonade", book=book, **kwargs)
    assert r.status == "invalid"
    assert r.gallons is None
    assert r.ingredients == () and r.steps == ()


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_invalid(book, name):
    """Covers: AC-2 (wrong), EC-10. A blank recipe name is invalid."""
    assert scale_recipe(name, gallons=2, book=book).status == "invalid"


def test_invalid_beats_no_recipe(book):
    """Covers: AC-2 (wrong), EC-10. Unknown recipe with gallons -2 is invalid, not no_recipe."""
    assert scale_recipe("iced tea", gallons=-2, book=book).status == "invalid"


def test_valid_gallons_with_valid_guests_is_ok(book):
    """Covers: AC-2 (right), EC-6 (extra). Valid gallons and valid guests together give ok, gallons used."""
    r = scale_recipe("lemonade", gallons=2, guests=10, book=book)
    assert r.status == "ok" and r.gallons == 2 and r.from_guests is False


def test_ok_result_fields_and_frozen(book):
    """Covers: AC-2 (right), EC-3 (extra). Results are frozen dataclasses."""
    r = scale_recipe("lemonade", gallons=1, book=book)
    with pytest.raises(Exception):
        r.status = "invalid"  # type: ignore[misc]
    with pytest.raises(Exception):
        r.ingredients[0].amount = F(1)  # type: ignore[misc]


def test_large_guest_count(book):
    """Covers: AC-2 (boundary), EC-5 (extra). 1000 guests is 40 gallons and 280 oz."""
    r = scale_recipe("lemonade", guests=1000, book=book)
    assert r.gallons == 40 and r.ingredients[0].amount == 280


def test_scaling_is_pure(book):
    """Covers: AC-2 (right), EC-3 (extra). The same call twice gives equal results."""
    assert scale_recipe("lemonade", gallons=6, book=book) == scale_recipe("lemonade", gallons=6, book=book)

"""AC-3 (bad input: EC-13) and AC-4 (the tool's text, spec 4.4, EC-16 grammar).
Bad raw arguments (EC-21) are in test_bev_args.py.

Unit tests: Appendix A catalog from tmp_path, no Ollama, no network (NFR-3).
"""

from __future__ import annotations

import re

import pytest

from blc.tools.bev_tools import DrinkRequest, calculate_bev_item

PKG = "Coffee, decaf, tea, iced water & juice"
SINGULAR_BUGS = re.compile(r"\b1 (gallons|cambros|cups)\b", re.IGNORECASE)


def calc(catalog, item, drinks=(), guests=None):
    return calculate_bev_item(item, drinks, guests, catalog)


def assert_invalid(r):
    assert r.status == "invalid"
    assert r.text.strip().lower().startswith("invalid")
    assert r.lines == ()
    assert r.drinks == ()


# ---------------------------------------------------------------- EC-13 invalid (calculate_bev_item)

def test_ec13_item_not_in_bev_items(catalog):
    """Covers: AC-3 (wrong), EC-13. item 'pans' is invalid and does not raise."""
    assert_invalid(calc(catalog, "pans", [DrinkRequest("Coffee", 5, "gal")]))


@pytest.mark.parametrize("item", ["", "Cambros", "gallon", "all"])
def test_item_must_match_exactly(catalog, item):
    """Covers: AC-3 (wrong, boundary), spec 4.2. Only the five BEV_ITEMS values are items."""
    assert calc(catalog, item, [DrinkRequest("Coffee", 5, "gal")]).status == "invalid"


@pytest.mark.parametrize("qty", [0, -1, -0.5, 0.0])
def test_ec13_quantity_not_positive(catalog, qty):
    """Covers: AC-3 (wrong, boundary), EC-13. Quantity 0 or negative is invalid."""
    assert_invalid(calc(catalog, "cambros", [DrinkRequest("Coffee", qty, "gal")]))


def test_quantity_just_above_zero_is_valid(catalog):
    """Covers: AC-3 (boundary), spec 4.2. A tiny positive quantity is not invalid."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee", 0.5, "gal")])
    assert r.status == "ok"


@pytest.mark.parametrize("guests", [0, -5, 2.5])
def test_ec13_guests_not_a_positive_integer(catalog, guests):
    """Covers: AC-3 (wrong, boundary), EC-13. guests 0, -5 or 2.5 is invalid."""
    assert_invalid(calc(catalog, "cups", [DrinkRequest("Coffee")], guests=guests))


def test_guests_one_is_valid(catalog):
    """Covers: AC-3 (boundary), spec 4.2. guests = 1 is the smallest valid value."""
    assert calc(catalog, "gallons", guests=1).status == "ok"


def test_invalid_guests_even_for_item_that_ignores_them(catalog):
    """Covers: AC-3 (wrong), spec 4.2. guests, when given, must be an integer >= 1 for every item."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "gal")], guests=0)
    assert r.status == "invalid"


def test_ec13_unit_quarts(catalog):
    """Covers: AC-3 (wrong), EC-13. Unit 'quarts' is invalid."""
    assert_invalid(calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "quarts")]))


def test_ec13_each_on_gallon_item(catalog):
    """Covers: AC-3 (wrong), EC-13. Unit 'each' on Coffee is invalid."""
    assert_invalid(calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "each")]))


def test_ec13_gallon_on_each_item(catalog):
    """Covers: AC-3 (wrong), EC-13. Unit 'gallon' on Oatmilk is invalid."""
    assert_invalid(calc(catalog, "gallons", [DrinkRequest("Oatmilk", 2, "gallon")]))


@pytest.mark.parametrize("unit", [None, "gallons", "each"])
def test_ec13_quantity_on_package(catalog, unit):
    """Covers: AC-3 (wrong), EC-13. A quantity on a package is invalid whatever the unit."""
    assert_invalid(calc(catalog, "cambros", [DrinkRequest(PKG, 5, unit)], guests=70))


def test_invalid_beats_not_on_menu(catalog):
    """Covers: AC-3 (wrong), spec 4.3 precedence. invalid wins over not_on_menu."""
    r = calc(catalog, "pans", [DrinkRequest("Hot chocolate", 4, "gal")])
    assert r.status == "invalid"


def test_invalid_beats_need_info(catalog):
    """Covers: AC-3 (wrong), spec 4.3 precedence. Bad guests with a missing amount is invalid, not need_info."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee")], guests=-5)
    assert r.status == "invalid"


# ---------------------------------------------------------------- AC-4 text: ok

def test_text_ok_cambros_example(catalog):
    """Covers: AC-4 (right), EC-3. Text names each drink with its gallons and each cambro line with its count."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "gal"), DrinkRequest("Lemonade", 3, "gal")])
    assert "Coffee: 5 gal" in r.text
    assert "Lemonade: 3 gal" in r.text
    assert "5 gal cambro: 2" in r.text


def test_text_matches_spec_example(catalog):
    """Covers: AC-4 (right), spec 4.4 example. Iced tea 4 gal + Peach tea 2 gal for cambros: only the required
    parts (each drink with its amount, each cambro line with its count) are checked, not the wording."""
    r = calc(catalog, "cambros", [DrinkRequest("Iced tea", 4, "gal"), DrinkRequest("Peach tea", 2, "gal")])
    assert "Iced tea: 4 gal" in r.text and "Peach tea: 2 gal" in r.text
    assert "5 gal cambro: 1" in r.text
    assert "2 gal cambro: 1" in r.text


def test_text_from_guests(catalog):
    """Covers: AC-4 (right), EC-4. A drink sized from guests says 'from 70 guests'."""
    r = calc(catalog, "cambros", [DrinkRequest("Lemonade")], guests=70)
    assert "Lemonade: 3 gal" in r.text
    assert "from 70 guests" in r.text


def test_text_no_from_guests_when_amount_given(catalog):
    """Covers: AC-4 (wrong), spec 4.4. 'from N guests' appears only when from_guests is True."""
    r = calc(catalog, "cambros", [DrinkRequest("Lemonade", 7, "gal")], guests=70)
    assert "from 70 guests" not in r.text


def test_text_each_amount(catalog):
    """Covers: AC-4 (right), spec 4.4. An each drink reads 'Oatmilk: 2 each'."""
    r = calc(catalog, "gallons", [DrinkRequest("Oatmilk", 2, "each")])
    assert "Oatmilk: 2 each" in r.text


def test_text_gallons_each(catalog):
    """Covers: AC-4 (right), EC-5. gallons_each text has the gallons and the guest count."""
    r = calc(catalog, "gallons", guests=75)
    assert "3" in r.text and "75" in r.text
    assert "gallon" in r.text.lower()


def test_text_supplies_ticks_and_cup_note(catalog):
    """Covers: AC-4 (right), EC-7. Supply names, 'bring' for ticks, and a note that cups need guests."""
    r = calc(catalog, "supplies", [DrinkRequest("Coffee")])
    text = r.text
    for name in ("Cocktail napkins", "Creamer", "Stir sticks", "Sugar"):
        assert name in text
    assert "bring" in text.lower()
    assert "cup" in text.lower() and "guests" in text.lower()
    # No cup line is listed (the note may mention cups in words, so only the lines are checked).
    assert not any(l.supply in ("hot-cups", "cold-cups") for l in r.lines)


def test_text_cups_quantities(catalog):
    """Covers: AC-4 (right), EC-6. Cup lines show their counts."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee"), DrinkRequest("Lemonade")], guests=70)
    assert "hot-cups: 120" in r.text
    assert "cold-cups: 120" in r.text


def test_text_cups_each(catalog):
    """Covers: AC-4 (right), EC-14. cups_each text has the cup count, the guest count, and says it applies to hot and to cold cups."""
    r = calc(catalog, "cups", guests=70)
    text = r.text.lower()
    assert "120" in text and "70" in text
    assert "hot" in text and "cold" in text


def test_text_cups_each_boundary_counts(catalog):
    """Covers: AC-4 (boundary), EC-14. The text follows the guests (150 guests -> 250)."""
    r = calc(catalog, "cups", guests=150)
    assert "250" in r.text and "150" in r.text


# ---------------------------------------------------------------- AC-4 text: grammar (EC-16)

def test_ec16_one_gallon_singular(catalog):
    """Covers: AC-4 (boundary), EC-16. gallons for 25 guests says '1 gallon', never '1 gallons'."""
    r = calc(catalog, "gallons", guests=25)
    assert "1 gallon" in r.text
    assert "1 gallons" not in r.text


def test_ec16_no_one_cambros(catalog):
    """Covers: AC-4 (boundary), EC-16. Lemonade 7 gal gives 1 + 1 cambros but the text never says '1 cambros'."""
    r = calc(catalog, "cambros", [DrinkRequest("Lemonade", 7, "gallons")])
    assert "1 cambros" not in r.text


@pytest.mark.parametrize(
    "item, drinks, guests",
    [
        ("gallons", [], 25),
        ("gallons", [], 37),
        ("cambros", [DrinkRequest("Lemonade", 7, "gal")], None),
        ("cambros", [DrinkRequest("Lemonade", 1, "gal")], None),
        ("cambros", [DrinkRequest("Lemonade")], 12),
        ("gallons", [DrinkRequest("Coffee")], 25),
        ("everything", [DrinkRequest("Coffee")], 1),
        ("cups", [DrinkRequest("Coffee")], 1),
    ],
)
def test_ec16_no_singular_bugs_anywhere(catalog, item, drinks, guests):
    """Covers: AC-4 (boundary), EC-16. Whole-word '1 gallons', '1 cambros', '1 cups' never appear in any ok text."""
    r = calc(catalog, item, drinks, guests=guests)
    assert r.status == "ok"
    assert not SINGULAR_BUGS.search(r.text), r.text


# ---------------------------------------------------------------- AC-4 text: not_on_menu

@pytest.mark.parametrize(
    "drinks",
    [
        [DrinkRequest("Hot chocolate", 4, "gal")],
        [DrinkRequest("Hot chocolate", 4, "gal"), DrinkRequest("Coffee", 7, "gal")],
    ],
)
def test_text_not_on_menu_any_status(catalog, drinks):
    """Covers: AC-4 (right), EC-11. Each unknown name appears with 'not on the beverage menu', in both statuses."""
    r = calc(catalog, "cambros", drinks)
    assert "Hot chocolate" in r.text
    assert "not on the beverage menu" in r.text


def test_text_ok_without_unknown_has_no_menu_warning(catalog):
    """Covers: AC-4 (wrong), EC-11. No unknown drinks, so no 'not on the beverage menu' text."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee", 7, "gal")])
    assert "not on the beverage menu" not in r.text


# ---------------------------------------------------------------- AC-4 text: need_info

def test_text_need_info_amount_missing(catalog):
    """Covers: AC-4 (right), EC-12. need_info is one question ending in '?' naming gallons and guests."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee"), DrinkRequest("Lemonade")])
    assert r.text.strip().endswith("?")
    assert "gallons" in r.text.lower()
    assert "guests" in r.text.lower()


def test_text_need_info_cups_guests(catalog):
    """Covers: AC-4 (right), EC-12. cups without guests asks for guests."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")])
    assert r.text.strip().endswith("?")
    assert "guests" in r.text.lower()


def test_text_need_info_cups_no_drinks_no_guests(catalog):
    """Covers: AC-4 (right), EC-12. cups with nothing asks for guests."""
    r = calc(catalog, "cups")
    assert r.text.strip().endswith("?")
    assert "guests" in r.text.lower()


@pytest.mark.parametrize("item", ["cambros", "supplies", "everything"])
def test_text_need_info_no_drink(catalog, item):
    """Covers: AC-4 (right), EC-12. No drinks: the question names 'drink'."""
    r = calc(catalog, item, [], guests=70)
    assert r.text.strip().endswith("?")
    assert "drink" in r.text.lower()


def test_text_need_info_gallons_no_drinks_no_guests(catalog):
    """Covers: AC-4 (right), EC-12. gallons with nothing asks for guests."""
    r = calc(catalog, "gallons")
    assert r.text.strip().endswith("?")
    assert "guests" in r.text.lower()


# ---------------------------------------------------------------- AC-4 text: invalid

INVALID_CASES = [
    ("pans", [DrinkRequest("Coffee", 5, "gal")], None),
    ("cambros", [DrinkRequest("Coffee", 0, "gal")], None),
    ("cups", [DrinkRequest("Coffee")], -5),
    ("cambros", [DrinkRequest("Coffee", 5, "quarts")], None),
    ("cambros", [DrinkRequest(PKG, 5)], 70),
]


@pytest.mark.parametrize("item, drinks, guests", INVALID_CASES)
def test_text_invalid_starts_with_invalid(catalog, item, drinks, guests):
    """Covers: AC-4 (right), EC-13. invalid text starts with the word 'invalid'."""
    r = calc(catalog, item, drinks, guests=guests)
    assert r.status == "invalid"
    assert r.text.strip().lower().startswith("invalid")


@pytest.mark.parametrize("item, drinks, guests", INVALID_CASES)
def test_text_invalid_shows_expected_format(catalog, item, drinks, guests):
    """Covers: AC-4 (right), EC-13. invalid text shows the argument format: it contains "item", "drinks", "gallons" and "guests" with the double quotes."""
    text = calc(catalog, item, drinks, guests=guests).text
    for key in ('"item"', '"drinks"', '"gallons"', '"guests"'):
        assert key in text, (key, text)


@pytest.mark.parametrize("unit", [None, "gallons", "gal", "each"])
def test_text_invalid_package_amount_says_pass_guests_instead(catalog, unit):
    """Covers: AC-4 (right), EC-13, EC-21. An amount on a package gives an invalid text with the words
    "package", "instead" and "guests", plus the expected format."""
    r = calc(catalog, "cambros", [DrinkRequest(PKG, 3, unit)], guests=70)
    assert r.status == "invalid"
    low = r.text.lower()
    assert low.strip().startswith("invalid")
    for word in ("package", "instead", "guests"):
        assert word in low, (word, r.text)
    for key in ('"item"', '"drinks"', '"gallons"', '"guests"'):
        assert key in r.text


def test_text_invalid_other_reasons_need_not_mention_package(catalog):
    """Covers: AC-4 (wrong), spec 4.4. The package wording is for the package case only; an unrelated invalid
    input (item 'pans') still shows the format. Guards against asserting package text everywhere."""
    r = calc(catalog, "pans", [DrinkRequest("Coffee", 5, "gal")])
    assert r.status == "invalid"
    assert '"gallons"' in r.text


def test_text_is_never_empty(catalog):
    """Covers: AC-4 (boundary). Every status gives non-empty text."""
    results = [
        calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "gal")]),
        calc(catalog, "cambros", [DrinkRequest("Eggnog", 5, "gal")]),
        calc(catalog, "cambros", [DrinkRequest("Coffee")]),
        calc(catalog, "pans"),
    ]
    assert [r.status for r in results] == ["ok", "not_on_menu", "need_info", "invalid"]
    assert all(r.text.strip() for r in results)

"""AC-1 / AC-2 for the revision 1 additions: EC-14 (cups with no drink, cups_each) and
EC-15 (short drink names).

Unit tests: Appendix A catalog from tmp_path, no Ollama, no network (NFR-3).
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from blc.pull_sheet import GALLON
from blc.tools.bev_tools import DrinkAmount, DrinkRequest, calculate_bev_item

PKG = "Coffee, decaf, tea, iced water & juice"


def calc(catalog, item, drinks=(), guests=None):
    return calculate_bev_item(item, drinks, guests, catalog)


# ---------------------------------------------------------------- EC-14 cups, no drinks

@pytest.mark.parametrize(
    "guests, expected",
    [(20, 30), (50, 70), (70, 120), (100, 150), (150, 250)],
)
def test_ec14_cups_each_for_guests(catalog, guests, expected):
    """Covers: AC-1 (right), EC-14. cups with no drinks: ok, cups_each = guests + extras, lines (), gallons_each None."""
    r = calc(catalog, "cups", guests=guests)
    assert r.status == "ok"
    assert r.cups_each == expected
    assert r.lines == ()
    assert r.drinks == ()
    assert r.gallons_each is None


@pytest.mark.parametrize(
    "guests, expected",
    [(1, 11), (21, 41), (51, 101), (101, 201)],
)
def test_ec14_cups_each_tier_boundaries(catalog, guests, expected):
    """Covers: AC-1 (boundary), EC-14. cups_each follows the extras tiers just past each limit."""
    assert calc(catalog, "cups", guests=guests).cups_each == expected


def test_ec14_cups_each_none_when_drinks_given(catalog):
    """Covers: AC-1 (wrong), EC-14. With drinks, cups come back as lines and cups_each is None."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")], guests=70)
    assert r.status == "ok"
    assert r.cups_each is None
    assert [(l.supply, l.quantity) for l in r.lines] == [("hot-cups", 120)]


def test_cups_each_none_for_other_items(catalog):
    """Covers: AC-1 (wrong), spec 3.1. cups_each is only set for item cups with no drinks."""
    assert calc(catalog, "gallons", guests=70).cups_each is None
    assert calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "gal")]).cups_each is None


def test_gallons_each_none_for_cups_without_drinks(catalog):
    """Covers: AC-1 (wrong), EC-14. gallons_each stays None for cups."""
    assert calc(catalog, "cups", guests=70).gallons_each is None


def test_cups_no_drinks_invalid_guests_still_invalid(catalog):
    """Covers: AC-1 (wrong, boundary), spec 4.2. cups with no drinks and guests 0 is invalid, not ok."""
    assert calc(catalog, "cups", guests=0).status == "invalid"


# ---------------------------------------------------------------- EC-15 short names

FIVE = [
    DrinkRequest("coffee"),
    DrinkRequest("decaf"),
    DrinkRequest("tea"),
    DrinkRequest("iced water"),
    DrinkRequest("juice"),
]


def test_ec15_short_names_equal_package(catalog, pair_lines):
    """Covers: AC-1 (right), EC-15. coffee/decaf/tea/iced water/juice at 70 guests -> five drinks at 3 gal, five 5 gal cambros."""
    r = calc(catalog, "cambros", FIVE, guests=70)
    assert r.status == "ok"
    assert r.not_on_menu == ()
    assert [d.drink for d in r.drinks] == ["Coffee", "Decaf", "Hot water", "Iced water", "Orange juice"]
    assert all(d.amount == 3 and d.unit == GALLON and d.from_guests for d in r.drinks)
    assert pair_lines(r.lines) == [("5 gal cambro", 5)]
    package = calc(catalog, "cambros", [DrinkRequest(PKG)], guests=70)
    assert r.lines == package.lines


def test_ec15_short_names_agree_with_pull_sheet(catalog, sheet_pairs, pair_lines):
    """Covers: AC-2 (right), EC-15. Cambro lines for the short names equal build_pull_sheet for the equivalent BEO."""
    r = calc(catalog, "everything", FIVE, guests=70)
    beo = [(n, 70, "") for n in ("Coffee", "Decaf", "Hot water", "Iced water", "Orange juice")]
    assert r.status == "ok"
    assert pair_lines(r.lines) == sheet_pairs(70, beo)


@pytest.mark.parametrize("name", ["tea", "Tea", "  TEA  ", "hot tea", "Hot Tea"])
def test_ec15_tea_and_hot_tea_are_hot_water(catalog, name):
    """Covers: AC-1 (right, boundary), EC-15. 'tea' and 'hot tea' resolve to Hot water after normalisation."""
    r = calc(catalog, "cambros", [DrinkRequest(name, 3, "gal")])
    assert r.status == "ok"
    assert [d.drink for d in r.drinks] == ["Hot water"]
    assert r.not_on_menu == ()


@pytest.mark.parametrize("name", ["juice", "Juice", " JUICE "])
def test_ec15_juice_is_orange_juice(catalog, name):
    """Covers: AC-1 (right), EC-15. 'juice' resolves to Orange juice."""
    r = calc(catalog, "cambros", [DrinkRequest(name, 3, "gal")])
    assert [d.drink for d in r.drinks] == ["Orange juice"]


@pytest.mark.parametrize(
    "name, expected",
    [("iced tea", "Iced tea"), ("peach tea", "Peach tea"), ("Iced Tea", "Iced tea")],
)
def test_ec15_iced_and_peach_tea_keep_their_own_items(catalog, name, expected):
    """Covers: AC-1 (right), EC-15. The short-name rule does not capture 'iced tea' or 'peach tea'."""
    r = calc(catalog, "cambros", [DrinkRequest(name, 3, "gal")])
    assert [d.drink for d in r.drinks] == [expected]


@pytest.mark.parametrize("name", ["green tea", "tea bags", "apple juice", "tea and juice"])
def test_short_names_only_match_exactly(catalog, name):
    """Covers: AC-1 (wrong, boundary), EC-15 / spec 4.1. Short names are exact: anything longer that matches nothing is not on the menu."""
    r = calc(catalog, "cambros", [DrinkRequest(name, 3, "gal")])
    assert r.status == "not_on_menu"
    assert r.not_on_menu == (name,)


def test_short_name_and_full_name_dedupe(catalog):
    """Covers: AC-1 (boundary), EC-15, EC-10. 'tea' and 'Hot water' are one item, larger amount wins."""
    r = calc(catalog, "cambros", [DrinkRequest("tea", 2, "gal"), DrinkRequest("Hot water", 4, "gal")])
    assert r.drinks == (DrinkAmount("Hot water", Fraction(4), GALLON, False),)

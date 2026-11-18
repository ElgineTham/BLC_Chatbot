"""AC-1 (calculator values, EC-1 to EC-12) and AC-2 (agreement with build_pull_sheet).
EC-14 (cups without a drink) and EC-15 (short names) are in test_bev_cups_names.py.

Unit tests: Appendix A catalog from tmp_path, no Ollama, no network (NFR-3).
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from blc.pull_sheet import EACH, GALLON
from blc.tools.bev_tools import (
    BEV_ITEMS,
    BEV_STATUSES,
    BevResult,
    DrinkAmount,
    DrinkRequest,
    calculate_bev_item,
)

PKG = "Coffee, decaf, tea, iced water & juice"
CAMBRO_5_1 = ("5 gal cambro", 1)
CAMBRO_2_1 = ("2 gal cambro", 1)


def calc(catalog, item, drinks=(), guests=None):
    return calculate_bev_item(item, drinks, guests, catalog)


def gal(menu, qty, unit=None):
    return DrinkRequest(menu, qty, unit)


# ---------------------------------------------------------------- constants / shape

def test_constants_match_contract():
    """Covers: AC-1 (right). Contract constants and result type."""
    assert BEV_ITEMS == ("gallons", "cambros", "cups", "supplies", "everything")
    assert BEV_STATUSES == ("ok", "need_info", "not_on_menu", "invalid")


def test_result_is_bevresult_with_valid_status(catalog):
    """Covers: AC-1 (right). Every result is a BevResult whose status is in BEV_STATUSES."""
    r = calc(catalog, "cambros", [gal("Lemonade", 7, "gallons")])
    assert isinstance(r, BevResult)
    assert r.status in BEV_STATUSES


# ---------------------------------------------------------------- EC-1, EC-2, EC-3 cambros

def test_ec1_lemonade_7_gal(catalog, pair_lines):
    """Covers: AC-1 (right), EC-1. 7 gal -> one 5 gal and one 2 gal cambro."""
    r = calc(catalog, "cambros", [gal("Lemonade", 7, "gallons")])
    assert r.status == "ok"
    assert pair_lines(r.lines) == [CAMBRO_5_1, CAMBRO_2_1]
    assert r.drinks == (DrinkAmount("Lemonade", Fraction(7), GALLON, False),)
    assert r.not_on_menu == ()
    assert r.gallons_each is None


@pytest.mark.parametrize(
    "qty, expected",
    [
        (3, [CAMBRO_5_1]),
        (2.5, [CAMBRO_5_1]),
        (12, [("5 gal cambro", 2), CAMBRO_2_1]),
        (5, [CAMBRO_5_1]),
    ],
)
def test_ec2_cambro_packing(catalog, pair_lines, qty, expected):
    """Covers: AC-1 (right, boundary), EC-2. 3 gal is one 5 gal cambro (not 2+1); 2.5 -> one 5 gal; 12 -> 2x5 + 2."""
    r = calc(catalog, "cambros", [gal("Lemonade", qty, "gal")])
    assert r.status == "ok"
    assert pair_lines(r.lines) == expected


def test_ec2_fractional_amount_is_exact(catalog):
    """Covers: AC-1 (boundary), EC-2. 2.5 gal is kept as the exact Fraction 5/2."""
    r = calc(catalog, "cambros", [gal("Lemonade", 2.5, "gallons")])
    assert r.drinks[0].amount == Fraction(5, 2)
    assert isinstance(r.drinks[0].amount, Fraction)


def test_ec3_coffee_5_plus_lemonade_3(catalog, pair_lines):
    """Covers: AC-1 (right), EC-3. Each drink gets its own cambro: 2 x 5 gal."""
    r = calc(catalog, "cambros", [gal("Coffee", 5, "gallons"), gal("Lemonade", 3, "gallons")])
    assert r.status == "ok"
    assert pair_lines(r.lines) == [("5 gal cambro", 2)]
    assert [d.drink for d in r.drinks] == ["Coffee", "Lemonade"]
    assert [d.amount for d in r.drinks] == [Fraction(5), Fraction(3)]


def test_unit_none_means_items_own_unit(catalog, pair_lines):
    """Covers: AC-1 (right), spec 4.2 step 1. unit None on a gallon item means gallons."""
    r = calc(catalog, "cambros", [DrinkRequest("Lemonade", 7)])
    assert r.status == "ok"
    assert pair_lines(r.lines) == [CAMBRO_5_1, CAMBRO_2_1]
    assert r.drinks[0].unit == GALLON


@pytest.mark.parametrize("unit", ["gallon", "gallons", "gal", "GALLONS", "Gal"])
def test_gallon_unit_spellings(catalog, unit):
    """Covers: AC-1 (right), spec 3.1 DrinkRequest.unit. Gallon unit is case-insensitive."""
    r = calc(catalog, "cambros", [gal("Lemonade", 7, unit)])
    assert r.status == "ok"
    assert r.drinks[0].amount == 7


def test_oatmilk_each(catalog):
    """Covers: AC-1 (right), spec 4.2. Oatmilk 2 each is an each amount, no cambro lines."""
    r = calc(catalog, "gallons", [gal("Oatmilk", 2, "each")])
    assert r.status == "ok"
    assert r.drinks == (DrinkAmount("Oatmilk", Fraction(2), EACH, False),)
    assert r.lines == ()


def test_oatmilk_each_unit_case_insensitive(catalog):
    """Covers: AC-1 (right). 'EACH' is accepted for an each item."""
    r = calc(catalog, "gallons", [gal("Oatmilk", 2, "EACH")])
    assert r.status == "ok"
    assert r.drinks[0].unit == EACH


# ---------------------------------------------------------------- EC-4, EC-5 from guests

def test_ec4_lemonade_from_70_guests(catalog, pair_lines):
    """Covers: AC-1 (right), EC-4. 70 guests -> 3 gal, from_guests True, one 5 gal cambro."""
    r = calc(catalog, "cambros", [DrinkRequest("Lemonade")], guests=70)
    assert r.status == "ok"
    assert r.drinks == (DrinkAmount("Lemonade", Fraction(3), GALLON, True),)
    assert pair_lines(r.lines) == [CAMBRO_5_1]


def test_quantity_beats_guests(catalog):
    """Covers: AC-1 (right), spec 4.2 step 1. A given quantity is used and from_guests is False."""
    r = calc(catalog, "cambros", [gal("Lemonade", 7, "gal")], guests=70)
    assert r.drinks == (DrinkAmount("Lemonade", Fraction(7), GALLON, False),)


@pytest.mark.parametrize(
    "guests, expected",
    [(1, 1), (12, 1), (25, 1), (37, 1), (38, 2), (62, 2), (63, 3), (75, 3), (100, 4)],
)
def test_ec5_gallons_each_for_guests(catalog, guests, expected):
    """Covers: AC-1 (right, boundary), EC-5. 25 guests per gallon, half rounds up, minimum 1."""
    r = calc(catalog, "gallons", guests=guests)
    assert r.status == "ok"
    assert r.gallons_each == expected
    assert r.drinks == ()
    assert r.lines == ()


def test_gallons_with_drink_and_guests(catalog):
    """Covers: AC-1 (right). gallons + drink + guests 75: Coffee 3 gal from guests; gallons_each is None."""
    r = calc(catalog, "gallons", [DrinkRequest("Coffee")], guests=75)
    assert r.status == "ok"
    assert r.drinks == (DrinkAmount("Coffee", Fraction(3), GALLON, True),)
    assert r.gallons_each is None
    assert r.lines == ()


def test_oatmilk_gets_no_amount_from_guests(catalog):
    """Covers: AC-1 (wrong), spec 4.2 step 2, 4.3. An each item is never sized from guests: no amount for
    Oatmilk, no gallon drink lacks an amount (status ok), so no drinks and no lines."""
    r = calc(catalog, "gallons", [DrinkRequest("Oatmilk")], guests=70)
    assert r.status == "ok"
    assert r.drinks == ()
    assert r.lines == ()
    assert r.not_on_menu == ()


# ---------------------------------------------------------------- EC-6 cups, EC-7 supplies, EC-8 everything

def test_ec6_cups_coffee_and_lemonade(catalog, pair_lines):
    """Covers: AC-1 (right), EC-6. 70 guests -> 120 hot and 120 cold cups."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee"), DrinkRequest("Lemonade")], guests=70)
    assert r.status == "ok"
    assert dict(pair_lines(r.lines)) == {"hot-cups": 120, "cold-cups": 120}
    assert len(r.lines) == 2


def test_ec6_cups_hot_drinks_only_count_once(catalog, pair_lines):
    """Covers: AC-1 (right), EC-6. Coffee + Decaf share one hot-cups line of 120, no cold cups."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee"), DrinkRequest("Decaf")], guests=70)
    assert pair_lines(r.lines) == [("hot-cups", 120)]


@pytest.mark.parametrize(
    "guests, expected",
    [(1, 11), (20, 30), (21, 41), (50, 70), (51, 101), (100, 150), (101, 201)],
)
def test_cups_extra_tier_boundaries(catalog, pair_lines, guests, expected):
    """Covers: AC-1 (boundary), EC-6. Extras tiers: <=20 +10, <=50 +20, <=100 +50, else +100."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")], guests=guests)
    assert pair_lines(r.lines) == [("hot-cups", expected)]


def test_ec7_supplies_without_guests(catalog, pair_lines):
    """Covers: AC-1 (right), EC-7. No guests: guest-dependent cup lines are left out."""
    r = calc(catalog, "supplies", [DrinkRequest("Coffee")])
    assert r.status == "ok"
    assert dict(pair_lines(r.lines)) == {
        "Cocktail napkins": None,
        "Creamer": None,
        "Stir sticks": 1,
        "Sugar": 1,
    }
    assert len(r.lines) == 4
    assert not any("cup" in l.supply for l in r.lines)


def test_supplies_with_guests_include_cups(catalog, pair_lines):
    """Covers: AC-1 (right), spec 4.3. With guests, supplies includes the cup lines."""
    r = calc(catalog, "supplies", [DrinkRequest("Coffee")], guests=70)
    assert dict(pair_lines(r.lines)) == {
        "hot-cups": 120,
        "Cocktail napkins": None,
        "Creamer": None,
        "Stir sticks": 1,
        "Sugar": 1,
    }


def test_supplies_shared_supply_pulled_once(catalog, pair_lines):
    """Covers: AC-1 (right). Coffee + Hot water both need sugar and stir sticks: one line each, qty 1."""
    r = calc(catalog, "supplies", [DrinkRequest("Coffee"), DrinkRequest("Hot water")])
    q = pair_lines(r.lines)
    assert q.count(("Sugar", 1)) == 1
    assert q.count(("Stir sticks", 1)) == 1
    assert ("Tea packets", 1) in q


def test_ec8_everything_coffee_50_guests(catalog, pair_lines):
    """Covers: AC-1 (right), EC-8. Cambros first, then supplies, in the pull sheet order."""
    r = calc(catalog, "everything", [DrinkRequest("Coffee")], guests=50)
    assert r.status == "ok"
    assert r.drinks == (DrinkAmount("Coffee", Fraction(2), GALLON, True),)
    assert pair_lines(r.lines) == [
        ("2 gal cambro", 1),
        ("hot-cups", 70),
        ("Cocktail napkins", None),
        ("Creamer", None),
        ("Stir sticks", 1),
        ("Sugar", 1),
    ]


def test_everything_without_guests_leaves_out_guest_lines(catalog, pair_lines):
    """Covers: AC-1 (right), spec 4.3. everything with a gallon amount and no guests omits cup lines."""
    r = calc(catalog, "everything", [gal("Coffee", 2, "gal")])
    assert r.status == "ok"
    names = [s for s, _ in pair_lines(r.lines)]
    assert names[0] == "2 gal cambro"
    assert "hot-cups" not in names
    assert "Sugar" in names


def test_everything_puts_add_on_between_cambros_and_supplies(catalog, pair_lines):
    """Covers: AC-1 (right), spec 4.3. Order is cambro lines, then add-on lines (Oatmilk), then supplies."""
    r = calc(
        catalog,
        "everything",
        [gal("Coffee", 5, "gal"), gal("Oatmilk", 2, "each")],
        guests=70,
    )
    names = [s for s, _ in pair_lines(r.lines)]
    assert names.index("5 gal cambro") < names.index("Oatmilk") < names.index("hot-cups")
    assert ("Oatmilk", 2) in pair_lines(r.lines)


# ---------------------------------------------------------------- EC-9 package, EC-10 names

def test_ec9_package_cambros(catalog, pair_lines):
    """Covers: AC-1 (right), EC-9. Package for 70 guests: five drinks at 3 gal, five 5 gal cambros."""
    r = calc(catalog, "cambros", [DrinkRequest(PKG)], guests=70)
    assert r.status == "ok"
    assert [d.drink for d in r.drinks] == ["Coffee", "Decaf", "Hot water", "Iced water", "Orange juice"]
    assert all(d.amount == 3 and d.unit == GALLON and d.from_guests for d in r.drinks)
    assert pair_lines(r.lines) == [("5 gal cambro", 5)]


def test_package_name_is_normalised(catalog):
    """Covers: AC-1 (right), spec 4.1. A lower-case package name still resolves."""
    r = calc(catalog, "cambros", [DrinkRequest(PKG.lower())], guests=70)
    assert r.status == "ok"
    assert len(r.drinks) == 5


def test_package_without_guests_needs_info(catalog):
    """Covers: AC-1 (wrong), spec 4.2 step 3. A package with no guests has no amounts, so need_info."""
    r = calc(catalog, "cambros", [DrinkRequest(PKG)])
    assert r.status == "need_info"
    assert r.lines == ()


@pytest.mark.parametrize("name", ["coffee", "Coffee", "Fresh-brewed coffee", "  COFFEE  "])
def test_ec10_coffee_names_resolve(catalog, name):
    """Covers: AC-1 (right), EC-10. Names and also_written_as resolve to Coffee."""
    r = calc(catalog, "cambros", [gal(name, 7, "gal")])
    assert r.status == "ok"
    assert [d.drink for d in r.drinks] == ["Coffee"]
    assert r.not_on_menu == ()


@pytest.mark.parametrize("order", [0, 1])
def test_ec10_duplicates_keep_larger_amount(catalog, pair_lines, order):
    """Covers: AC-1 (boundary), EC-10. 'coffee' 2 gal + 'Fresh-brewed coffee' 5 gal -> one Coffee at 5 (not summed)."""
    reqs = [gal("coffee", 2, "gal"), gal("Fresh-brewed coffee", 5, "gal")]
    if order:
        reqs.reverse()
    r = calc(catalog, "cambros", reqs)
    assert [d.drink for d in r.drinks] == ["Coffee"]
    assert r.drinks[0].amount == 5
    assert pair_lines(r.lines) == [CAMBRO_5_1]


def test_drinks_keep_request_order(catalog):
    """Covers: AC-1 (right), spec 3.1. drinks are in request order."""
    r = calc(catalog, "cambros", [gal("Lemonade", 1, "gal"), gal("Coffee", 1, "gal")])
    assert [d.drink for d in r.drinks] == ["Lemonade", "Coffee"]


# ---------------------------------------------------------------- EC-11 not on menu, EC-12 need info

def test_ec11_only_unknown_drink(catalog):
    """Covers: AC-1 (wrong), EC-11. Hot chocolate alone -> not_on_menu, no lines, no drinks."""
    r = calc(catalog, "cambros", [gal("Hot chocolate", 4, "gal")])
    assert r.status == "not_on_menu"
    assert r.not_on_menu == ("Hot chocolate",)
    assert r.lines == ()
    assert r.drinks == ()


def test_ec11_unknown_plus_known(catalog, pair_lines):
    """Covers: AC-1 (right), EC-11. Unknown drink is reported, known one is calculated, status ok."""
    r = calc(catalog, "cambros", [gal("Hot chocolate", 4, "gal"), gal("Coffee", 7, "gal")])
    assert r.status == "ok"
    assert r.not_on_menu == ("Hot chocolate",)
    assert pair_lines(r.lines) == [CAMBRO_5_1, CAMBRO_2_1]
    assert [d.drink for d in r.drinks] == ["Coffee"]


def test_not_on_menu_names_are_stripped_and_in_order(catalog):
    """Covers: AC-1 (boundary), spec 3.1. not_on_menu holds stripped names in request order."""
    r = calc(
        catalog,
        "cambros",
        [gal("  Eggnog ", 1, "gal"), gal("Coffee", 1, "gal"), gal("Hot chocolate", 1, "gal")],
    )
    assert r.not_on_menu == ("Eggnog", "Hot chocolate")


def test_unknown_plus_known_without_amount_is_need_info(catalog):
    """Covers: AC-1 (wrong), spec 4.3. Some unknown, known one has no amount -> need_info with not_on_menu listed."""
    r = calc(catalog, "cambros", [DrinkRequest("Hot chocolate"), DrinkRequest("Coffee")])
    assert r.status == "need_info"
    assert r.not_on_menu == ("Hot chocolate",)


def test_ec12_cambros_no_amounts_no_guests(catalog):
    """Covers: AC-1 (wrong), EC-12. Coffee + Lemonade without quantities or guests -> need_info."""
    r = calc(catalog, "cambros", [DrinkRequest("Coffee"), DrinkRequest("Lemonade")])
    assert r.status == "need_info"
    assert r.lines == ()
    assert r.drinks == ()


def test_ec12_cups_without_guests(catalog):
    """Covers: AC-1 (wrong), EC-12. cups for Coffee with no guests -> need_info."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")])
    assert r.status == "need_info"
    assert r.lines == ()


@pytest.mark.parametrize("item", ["cambros", "supplies", "everything"])
def test_ec12_no_drinks_needs_info(catalog, item):
    """Covers: AC-1 (wrong, boundary), EC-12. Empty drinks list -> need_info for every drink-based item (cups no longer needs a drink, EC-14)."""
    r = calc(catalog, item, [], guests=70)
    assert r.status == "need_info"
    assert r.lines == ()


def test_ec12_cups_no_drinks_no_guests(catalog):
    """Covers: AC-1 (wrong), EC-12. cups with no drinks and no guests -> need_info (guests)."""
    r = calc(catalog, "cups")
    assert r.status == "need_info"
    assert r.cups_each is None
    assert r.lines == ()


def test_ec12_gallons_no_drinks_no_guests(catalog):
    """Covers: AC-1 (wrong), EC-12. gallons with neither drinks nor guests -> need_info."""
    r = calc(catalog, "gallons")
    assert r.status == "need_info"
    assert r.gallons_each is None


def test_everything_needs_amount_for_every_gallon_drink(catalog):
    """Covers: AC-1 (wrong), spec 4.3. One of two gallon drinks without an amount -> need_info."""
    r = calc(catalog, "everything", [gal("Coffee", 5, "gal"), DrinkRequest("Lemonade")])
    assert r.status == "need_info"


def test_gallons_item_needs_amount_for_every_gallon_drink(catalog):
    """Covers: AC-1 (wrong), spec 4.3. gallons with a drink but no amount and no guests -> need_info."""
    r = calc(catalog, "gallons", [DrinkRequest("Coffee")])
    assert r.status == "need_info"


def test_supplies_need_only_a_drink(catalog):
    """Covers: AC-1 (boundary), spec 4.3. supplies needs a drink but no amount and no guests."""
    r = calc(catalog, "supplies", [DrinkRequest("Lemonade")])
    assert r.status == "ok"
    assert [l.supply for l in r.lines] == ["Cocktail napkins"]


# ---------------------------------------------------------------- AC-2 agreement with build_pull_sheet

def _is_cambro(supply):
    return supply.endswith("cambro")


def _is_cup(supply):
    return supply in ("hot-cups", "cold-cups")


def _is_supply(supply):
    return not _is_cambro(supply) and supply != "Oatmilk"


FILTERS = {
    "cambros": _is_cambro,
    "cups": _is_cup,
    "supplies": _is_supply,
    "everything": lambda s: True,
}

AGREEMENT_CASES = [
    # id, item, drink requests, guests, equivalent BEO entries (name, qty, uom)
    ("ec1", "cambros", [("Lemonade", 7, "gallons")], 70, [("Lemonade", 7, "Gallon")]),
    ("ec2a", "cambros", [("Lemonade", 3, "gallons")], 70, [("Lemonade", 3, "Gallon")]),
    ("ec2b", "cambros", [("Lemonade", 2.5, "gallons")], 70, [("Lemonade", 2.5, "Gallon")]),
    ("ec2c", "cambros", [("Lemonade", 12, "gallons")], 70, [("Lemonade", 12, "Gallon")]),
    ("ec3", "cambros", [("Coffee", 5, "gal"), ("Lemonade", 3, "gal")], 70,
     [("Coffee", 5, "Gallon"), ("Lemonade", 3, "Gallon")]),
    ("ec4", "cambros", [("Lemonade", None, None)], 70, [("Lemonade", 70, "")]),
    ("ec6a", "cups", [("Coffee", None, None), ("Lemonade", None, None)], 70,
     [("Coffee", 70, ""), ("Lemonade", 70, "")]),
    ("ec6b", "cups", [("Coffee", None, None), ("Decaf", None, None)], 70,
     [("Coffee", 70, ""), ("Decaf", 70, "")]),
    ("ec7", "supplies", [("Coffee", None, None)], 70, [("Coffee", 70, "")]),
    ("ec8", "everything", [("Coffee", None, None)], 50, [("Coffee", 50, "")]),
    ("ec9-cambros", "cambros", [(PKG, None, None)], 70, [(PKG, 70, "")]),
    ("ec9-cups", "cups", [(PKG, None, None)], 70, [(PKG, 70, "")]),
    ("ec9-supplies", "supplies", [(PKG, None, None)], 70, [(PKG, 70, "")]),
    ("ec9-everything", "everything", [(PKG, None, None)], 70, [(PKG, 70, "")]),
    ("mixed", "everything",
     [("Coffee", 7, "gal"), ("Lemonade", None, None), ("Oatmilk", 2, "each")], 70,
     [("Coffee", 7, "Gallon"), ("Lemonade", 70, ""), ("Oatmilk", 2, "Each")]),
    ("hotwater-iced-tea", "supplies", [("Hot water", 3, "gal"), ("Iced tea", 3, "gal")], 30,
     [("Hot water", 3, "Gallon"), ("Iced tea", 3, "Gallon")]),
    ("big-event", "everything", [("Coffee", 10, "gal"), ("Iced water", 8, "gal")], 120,
     [("Coffee", 10, "Gallon"), ("Iced water", 8, "Gallon")]),
]


@pytest.mark.parametrize(
    "item, reqs, guests, beo",
    [c[1:] for c in AGREEMENT_CASES],
    ids=[c[0] for c in AGREEMENT_CASES],
)
def test_ac2_lines_equal_pull_sheet(catalog, sheet_pairs, pair_lines, item, reqs, guests, beo):
    """Covers: AC-2 (right). For status ok with guests, lines equal the matching lines of build_pull_sheet for the equivalent BEO."""
    drinks = [DrinkRequest(m, q, u) for m, q, u in reqs]
    r = calc(catalog, item, drinks, guests=guests)
    assert r.status == "ok"
    expected = [p for p in sheet_pairs(guests, beo) if FILTERS[item](p[0])]
    assert pair_lines(r.lines) == expected


@pytest.mark.parametrize("guests", [1, 20, 21, 70, 101])
def test_ac2_cambro_lines_do_not_depend_on_guests(catalog, pair_lines, guests):
    """Covers: AC-2 (boundary), spec 4.3. Cambro lines for given amounts are the same for any Guest Count."""
    r = calc(catalog, "cambros", [gal("Coffee", 5, "gal"), gal("Lemonade", 3, "gal")], guests=guests)
    assert pair_lines(r.lines) == [("5 gal cambro", 2)]


def test_ac2_every_item_but_gallons_is_covered():
    """Covers: AC-2 (right). The agreement cases exercise every BEV_ITEMS entry except gallons."""
    used = {c[1] for c in AGREEMENT_CASES}
    assert used == set(BEV_ITEMS) - {"gallons"}

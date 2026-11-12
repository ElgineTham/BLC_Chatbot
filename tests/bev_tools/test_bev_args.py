"""AC-5 (raw arguments, EC-17 to EC-20) and the bad-argument half of AC-3 (EC-21).

run_bev_tool takes the argument dict the chat model sends (spec 4.0). Unit tests: Appendix A
catalog from tmp_path, no Ollama, no network (NFR-3).
"""

from __future__ import annotations

import pytest

from blc.tools.bev_tools import BevResult, DrinkRequest, calculate_bev_item, run_bev_tool

PKG = "Coffee, decaf, tea, iced water & juice"
FIELDS = ("status", "drinks", "lines", "not_on_menu", "gallons_each", "cups_each")


def calc(catalog, item, drinks=(), guests=None):
    return calculate_bev_item(item, drinks, guests, catalog)


def same(a: BevResult, b: BevResult):
    for f in FIELDS:
        assert getattr(a, f) == getattr(b, f), (f, getattr(a, f), getattr(b, f))


@pytest.fixture
def ec1(catalog):
    """Lemonade 7 gal, cambros (EC-1)."""
    return calc(catalog, "cambros", [DrinkRequest("Lemonade", 7, "gallons")])


@pytest.fixture
def ec3(catalog):
    """Coffee 5 gal + Lemonade 3 gal, cambros (EC-3)."""
    return calc(catalog, "cambros", [DrinkRequest("Coffee", 5, "gal"), DrinkRequest("Lemonade", 3, "gal")])


@pytest.fixture
def ec4(catalog):
    """Lemonade from 70 guests, cambros (EC-4)."""
    return calc(catalog, "cambros", [DrinkRequest("Lemonade")], guests=70)


# ---------------------------------------------------------------- EC-17 expected shape

def test_ec17_one_drink_one_amount(catalog, ec1):
    """Covers: AC-5 (right), EC-17. drinks ['lemonade'] with gallons [7] equals EC-1."""
    r = run_bev_tool({"item": "cambros", "drinks": ["lemonade"], "gallons": [7]}, catalog)
    assert r.status == "ok"
    same(r, ec1)


def test_ec17_two_drinks_two_amounts(catalog, ec3):
    """Covers: AC-5 (right), EC-17. Amounts line up with drinks by position: equals EC-3."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5, 3]}, catalog)
    same(r, ec3)
    assert [(d.drink, d.amount) for d in r.drinks] == [("Coffee", 5), ("Lemonade", 3)]


def test_ec17_amounts_are_positional_not_sorted(catalog):
    """Covers: AC-5 (boundary), EC-17. Swapping the order swaps the amounts."""
    r = run_bev_tool({"item": "cambros", "drinks": ["lemonade", "coffee"], "gallons": [5, 3]}, catalog)
    assert [(d.drink, d.amount) for d in r.drinks] == [("Lemonade", 5), ("Coffee", 3)]


def test_ec17_numeric_string_amount(catalog, ec1):
    """Covers: AC-5 (right), EC-17. gallons ['7'] equals EC-1."""
    same(run_bev_tool({"item": "cambros", "drinks": ["lemonade"], "gallons": ["7"]}, catalog), ec1)


def test_decimal_string_amount(catalog, pair_lines):
    """Covers: AC-5 (right, boundary), spec 4.0. '2.5' is a number: 2.5 gal fits one 5 gal cambro."""
    r = run_bev_tool({"item": "cambros", "drinks": ["lemonade"], "gallons": ["2.5"]}, catalog)
    assert r.status == "ok"
    assert pair_lines(r.lines) == [("5 gal cambro", 1)]


def test_unknown_extra_keys_are_ignored(catalog, ec1):
    """Covers: AC-5 (right), spec 4.0. Unknown keys do not matter."""
    args = {"item": "cambros", "drinks": ["lemonade"], "gallons": [7], "unit": "gallons", "note": "hi"}
    same(run_bev_tool(args, catalog), ec1)


def test_oatmilk_number_is_a_count_of_pieces(catalog):
    """Covers: AC-5 (right), spec 4.0. gallons[i] for Oatmilk is in pieces (each)."""
    r = run_bev_tool({"item": "gallons", "drinks": ["oatmilk"], "gallons": [2]}, catalog)
    assert r.status == "ok"
    assert [(d.drink, d.amount, d.unit) for d in r.drinks] == [("Oatmilk", 2, "each")]
    assert "Oatmilk: 2 each" in r.text


def test_item_gallons_with_drinks_and_amounts(catalog):
    """Covers: AC-5 (right), spec 4.0. item gallons echoes the drinks with their amounts."""
    r = run_bev_tool({"item": "gallons", "drinks": ["coffee"], "gallons": [4]}, catalog)
    assert [(d.drink, d.amount, d.from_guests) for d in r.drinks] == [("Coffee", 4, False)]


# ---------------------------------------------------------------- EC-18 one amount, several drinks

def test_ec18_one_amount_applies_to_every_drink(catalog):
    """Covers: AC-5 (right), EC-18. gallons [5] with two drinks gives each 5 gal and two 5 gal cambros."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5]}, catalog)
    assert r.status == "ok"
    assert [(d.drink, d.amount) for d in r.drinks] == [("Coffee", 5), ("Lemonade", 5)]
    assert [(l.supply, l.quantity) for l in r.lines] == [("5 gal cambro", 2)]


def test_ec18_one_amount_as_string(catalog):
    """Covers: AC-5 (boundary), EC-18. gallons ['5'] is spread the same way."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade", "decaf"], "gallons": ["5"]}, catalog)
    assert [d.amount for d in r.drinks] == [5, 5, 5]


def test_ec18_one_amount_one_drink_is_plain(catalog, ec1):
    """Covers: AC-5 (boundary), EC-18. One number with one drink is just that drink's amount."""
    same(run_bev_tool({"item": "cambros", "drinks": ["lemonade"], "gallons": [7]}, catalog), ec1)


def test_gallons_length_mismatch_beyond_one_is_invalid(catalog):
    """Covers: AC-5 (wrong, boundary), spec 4.0. Two amounts for three drinks is invalid (only a single number is spread)."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade", "decaf"], "gallons": [5, 3]}, catalog)
    assert r.status == "invalid"


# ---------------------------------------------------------------- EC-19 not given

@pytest.mark.parametrize(
    "args",
    [
        {"item": "cups", "guests": 70},
        {"item": "cups", "drinks": [], "guests": 70},
        {"item": "cups", "drinks": None, "guests": 70},
        {"item": "cups", "drinks": None, "gallons": None, "guests": 70},
        {"item": "cups", "drinks": [], "gallons": [], "guests": 70},
    ],
)
def test_ec19_cups_drinks_not_given(catalog, args):
    """Covers: AC-5 (right, boundary), EC-19. Missing, null or empty drinks/gallons all mean not given: cups_each 120."""
    r = run_bev_tool(args, catalog)
    assert r.status == "ok"
    assert r.cups_each == 120


def test_ec19_guests_zero_means_not_given(catalog):
    """Covers: AC-5 (boundary), EC-19. guests 0 is 'not given', so a drink without an amount is need_info."""
    r = run_bev_tool({"item": "cambros", "drinks": ["lemonade"], "guests": 0}, catalog)
    assert r.status == "need_info"
    same(r, calc(catalog, "cambros", [DrinkRequest("Lemonade")]))


def test_ec19_guests_null_means_not_given(catalog):
    """Covers: AC-5 (boundary), EC-19. guests null behaves like missing."""
    r = run_bev_tool({"item": "supplies", "drinks": ["coffee"], "guests": None}, catalog)
    same(r, calc(catalog, "supplies", [DrinkRequest("Coffee")]))


def test_ec19_zero_amount_means_no_amount_for_that_drink(catalog):
    """Covers: AC-5 (boundary), EC-19. gallons [5, 0]: Lemonade has no amount, so need_info."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5, 0]}, catalog)
    assert r.status == "need_info"
    assert r.lines == ()


def test_ec19_null_amount_means_no_amount_for_that_drink(catalog):
    """Covers: AC-5 (boundary), EC-19. gallons [5, null]: need_info without guests."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5, None]}, catalog)
    assert r.status == "need_info"


def test_ec19_missing_amount_filled_from_guests(catalog):
    """Covers: AC-5 (right), EC-19. gallons [5, 0] with guests 70: Lemonade 3 gal from guests, Coffee 5 gal given."""
    r = run_bev_tool(
        {"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": [5, 0], "guests": 70}, catalog
    )
    assert r.status == "ok"
    assert [(d.drink, d.amount, d.from_guests) for d in r.drinks] == [("Coffee", 5, False), ("Lemonade", 3, True)]


@pytest.mark.parametrize("guests", ["70", 70.0, 70])
def test_ec19_guests_spellings(catalog, guests):
    """Covers: AC-5 (right, boundary), EC-19. 70, 70.0 and '70' are all 70."""
    r = run_bev_tool({"item": "cups", "guests": guests}, catalog)
    assert r.status == "ok"
    assert r.cups_each == 120


def test_guests_with_drinks_from_guests(catalog, ec4):
    """Covers: AC-5 (right), EC-19. drinks without gallons and guests 70 equals EC-4."""
    same(run_bev_tool({"item": "cambros", "drinks": ["lemonade"], "guests": 70}, catalog), ec4)


# ---------------------------------------------------------------- EC-20 other shapes accepted

def test_ec20_drinks_single_string(catalog, ec1):
    """Covers: AC-5 (right), EC-20. drinks 'lemonade' (a string) is one drink."""
    same(run_bev_tool({"item": "cambros", "drinks": "lemonade", "gallons": [7]}, catalog), ec1)


def test_ec20_drinks_mapping(catalog, ec3):
    """Covers: AC-5 (right), EC-20. drinks as {name: amount} equals EC-3, in key order."""
    same(run_bev_tool({"item": "cambros", "drinks": {"coffee": 5, "lemonade": 3}}, catalog), ec3)


def test_ec20_drinks_mapping_numeric_strings(catalog, ec3):
    """Covers: AC-5 (right), EC-20. Mapping amounts may be numeric strings."""
    same(run_bev_tool({"item": "cambros", "drinks": {"coffee": "5", "lemonade": "3"}}, catalog), ec3)


def test_ec20_drinks_mapping_key_order_is_request_order(catalog):
    """Covers: AC-5 (boundary), EC-20. Drinks come out in the mapping's key order."""
    r = run_bev_tool({"item": "cambros", "drinks": {"lemonade": 3, "coffee": 5}}, catalog)
    assert [d.drink for d in r.drinks] == ["Lemonade", "Coffee"]


@pytest.mark.parametrize(
    "drinks",
    [
        [{"menu": "lemonade", "quantity": 7, "unit": "gallons"}],
        [{"name": "lemonade", "quantity": 7}],
        [{"menu_name": "Lemonade", "gallons": 7}],
        [{"drink": "lemonade", "amount": "7"}],
    ],
)
def test_ec20_drinks_list_of_objects(catalog, ec1, drinks):
    """Covers: AC-5 (right), EC-20. Objects with menu/name/menu_name/drink and quantity/gallons/amount equal EC-1."""
    same(run_bev_tool({"item": "cambros", "drinks": drinks}, catalog), ec1)


def test_ec20_name_key_priority_first_present_wins(catalog):
    """Covers: AC-5 (boundary), spec 4.0. With both 'menu' and 'name', 'menu' (listed first) wins."""
    r = run_bev_tool({"item": "cambros", "drinks": [{"menu": "lemonade", "name": "coffee", "quantity": 7}]}, catalog)
    assert [d.drink for d in r.drinks] == ["Lemonade"]


def test_ec20_object_without_amount_uses_guests(catalog, ec4):
    """Covers: AC-5 (right), EC-20. drinks {'lemonade': null} with guests 70 equals EC-4."""
    same(run_bev_tool({"item": "cambros", "drinks": {"lemonade": None}, "guests": 70}, catalog), ec4)


def test_ec20_object_with_unit_each(catalog):
    """Covers: AC-5 (right), EC-20. An object's own unit is passed on: Oatmilk 2 each."""
    r = run_bev_tool({"item": "gallons", "drinks": [{"name": "oatmilk", "quantity": 2, "unit": "each"}]}, catalog)
    assert r.status == "ok"
    assert [(d.drink, d.amount, d.unit) for d in r.drinks] == [("Oatmilk", 2, "each")]


def test_ec20_object_with_bad_unit_is_invalid(catalog):
    """Covers: AC-5 (wrong), EC-20, EC-13. An object's unit 'quarts' is still invalid."""
    r = run_bev_tool({"item": "cambros", "drinks": [{"name": "coffee", "quantity": 2, "unit": "quarts"}]}, catalog)
    assert r.status == "invalid"


def test_ec20_empty_gallons_list_with_mapping_is_fine(catalog, ec3):
    """Covers: AC-5 (boundary), spec 4.0. An empty or null gallons list is 'not given', so it does not clash with a mapping."""
    for extra in ({"gallons": []}, {"gallons": None}):
        args = {"item": "cambros", "drinks": {"coffee": 5, "lemonade": 3}, **extra}
        same(run_bev_tool(args, catalog), ec3)


# ---------------------------------------------------------------- not on menu / package via raw args

def test_unknown_drink_by_raw_args(catalog):
    """Covers: AC-5 (wrong), EC-11. Hot chocolate through run_bev_tool is not_on_menu."""
    r = run_bev_tool({"item": "cambros", "drinks": ["hot chocolate"], "gallons": [4]}, catalog)
    assert r.status == "not_on_menu"
    assert r.not_on_menu == ("hot chocolate",)


def test_package_as_one_name(catalog):
    """Covers: AC-5 (right), EC-9. A package is passed as one name; guests size it."""
    r = run_bev_tool({"item": "cambros", "drinks": [PKG], "guests": 70}, catalog)
    assert r.status == "ok"
    assert [(l.supply, l.quantity) for l in r.lines] == [("5 gal cambro", 5)]


def test_package_with_an_amount_is_invalid(catalog):
    """Covers: AC-5 (wrong), spec 4.2 step 3. A gallons number for a package name is a quantity on a package: invalid."""
    r = run_bev_tool({"item": "cambros", "drinks": [PKG], "gallons": [5], "guests": 70}, catalog)
    assert r.status == "invalid"


def test_short_names_via_raw_args(catalog):
    """Covers: AC-5 (right), EC-15. 'tea' and 'juice' work through run_bev_tool."""
    r = run_bev_tool({"item": "cambros", "drinks": ["tea", "juice"], "guests": 70}, catalog)
    assert [d.drink for d in r.drinks] == ["Hot water", "Orange juice"]


# ---------------------------------------------------------------- EC-21 invalid, never raises

INVALID_ARGS = [
    {"drinks": ["coffee"], "gallons": [5]},
    {"item": "pans"},
    {"item": "cambros", "drinks": 5},
    {"item": "cambros", "drinks": [{"description": "Drinks named by the user"}]},
    {"item": "cambros", "drinks": ["coffee"], "gallons": [5, 3]},
    {"item": "cambros", "gallons": [5]},
    {"item": "cambros", "drinks": ["coffee"], "gallons": [-2]},
    {"item": "cambros", "drinks": ["coffee"], "gallons": ["seven"]},
    {"item": "cups", "guests": -5},
    {"item": "cups", "guests": 2.5},
    {"item": "cups", "guests": "seventy"},
    {"item": "cambros", "drinks": {"coffee": 5}, "gallons": [5]},
]


@pytest.mark.parametrize("args", INVALID_ARGS, ids=[str(i) for i in range(len(INVALID_ARGS))])
def test_ec21_invalid_and_never_raises(catalog, args):
    """Covers: AC-3 (wrong), EC-21. Each bad argument dict gives status invalid, with no lines or drinks, and does not raise."""
    r = run_bev_tool(args, catalog)
    assert r.status == "invalid"
    assert r.lines == ()
    assert r.drinks == ()


@pytest.mark.parametrize("args", INVALID_ARGS, ids=[str(i) for i in range(len(INVALID_ARGS))])
def test_ec21_invalid_text_shows_format(catalog, args):
    """Covers: AC-3 (wrong), AC-4 (right), EC-21. The invalid text starts with 'invalid' and contains "item", "drinks", "gallons" and "guests"."""
    text = run_bev_tool(args, catalog).text
    assert text.strip().lower().startswith("invalid")
    for key in ('"item"', '"drinks"', '"gallons"', '"guests"'):
        assert key in text, (key, text)


PACKAGE_GALLONS_ARGS = [
    {"item": "cambros", "drinks": [PKG], "gallons": [3]},
    {"item": "cambros", "drinks": [PKG], "gallons": [3], "guests": 70},
    {"item": "cambros", "drinks": PKG, "gallons": ["3"]},
    {"item": "cambros", "drinks": {PKG: 3}},
]


@pytest.mark.parametrize("args", PACKAGE_GALLONS_ARGS, ids=[str(i) for i in range(len(PACKAGE_GALLONS_ARGS))])
def test_ec21_package_amount_text_says_guests_instead(catalog, args):
    """Covers: AC-3 (wrong), AC-4 (right), EC-21. A gallons amount on the package, in any accepted shape, is
    invalid and the text contains "package", "instead" and "guests"."""
    r = run_bev_tool(args, catalog)
    assert r.status == "invalid"
    low = r.text.lower()
    assert low.strip().startswith("invalid")
    for word in ("package", "instead", "guests"):
        assert word in low, (word, r.text)
    for key in ('"item"', '"drinks"', '"gallons"', '"guests"'):
        assert key in r.text


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"item": None},
        {"item": ["cambros"]},
        {"item": 5},
        {"item": "cambros", "drinks": [None]},
        {"item": "cambros", "drinks": [5]},
        {"item": "cambros", "drinks": [["coffee"]]},
        {"item": "cups", "guests": [70]},
        {"item": "cups", "guests": {"n": 70}},
        {"item": "cambros", "drinks": ["coffee"], "gallons": [[5]]},
    ],
)
def test_odd_shapes_never_raise(catalog, args):
    """Covers: AC-3 (wrong, boundary), spec 4.0 / 3.1. run_bev_tool never raises for bad arguments: it returns a BevResult."""
    r = run_bev_tool(args, catalog)
    assert isinstance(r, BevResult)
    assert r.status == "invalid"


@pytest.mark.parametrize("gallons", [[-0.5], [5, -2], ["-1"]])
def test_negative_amount_anywhere_is_invalid(catalog, gallons):
    """Covers: AC-3 (wrong, boundary), spec 4.0. A negative number at any position is invalid."""
    r = run_bev_tool({"item": "cambros", "drinks": ["coffee", "lemonade"], "gallons": gallons}, catalog)
    assert r.status == "invalid"


def test_mapping_with_non_numeric_amount_is_invalid(catalog):
    """Covers: AC-3 (wrong), spec 4.0. drinks {'coffee': 'lots'} is a non-numeric string where a number is expected."""
    r = run_bev_tool({"item": "cambros", "drinks": {"coffee": "lots"}}, catalog)
    assert r.status == "invalid"


def test_valid_args_are_not_invalid(catalog):
    """Covers: AC-3 (right, boundary). The smallest valid call (item only, with guests) is not flagged invalid."""
    assert run_bev_tool({"item": "gallons", "guests": 1}, catalog).status == "ok"

"""Spec 020, AC-1 (cups text, EC-1 to EC-8 and EC-11) and AC-2 (nothing else changes, EC-9 and EC-10).

Only BevResult.text changes, and only for status ok with item "cups". Unit tests: Appendix A catalog from
tmp_path (conftest `catalog` fixture), no Ollama, no network, nothing read under data/ (NFR-2).
Wording is illustrative in the spec, so these tests check only the required parts.
"""

from __future__ import annotations

import re
from fractions import Fraction

import pytest

from blc.tools.bev_tools import DrinkRequest, calculate_bev_item, run_bev_tool

PKG = "Coffee, decaf, tea, iced water & juice"
FROM_GUESTS_SENTENCE = re.compile(r"\bfrom \d+ guests?\b", re.IGNORECASE)
AMOUNT_EACH = re.compile(r"\d+\s+each\b", re.IGNORECASE)


def calc(catalog, item, drinks=(), guests=None):
    return calculate_bev_item(item, drinks, guests, catalog)


def pairs(r):
    return [(l.supply, l.quantity) for l in r.lines]


def assert_no_drink_amounts(text):
    """Never in a cups ok text (spec 4.1): gallons, drink amounts, raw supply names, 'Drinks:' line."""
    low = text.lower()
    assert "gal" not in low, text
    assert not FROM_GUESTS_SENTENCE.search(text), text
    assert not AMOUNT_EACH.search(text), text
    assert "hot-cups" not in low and "cold-cups" not in low, text
    assert "drinks:" not in low, text


# ---------------------------------------------------------------- EC-1 / AC-1: one cup line

def test_ec1_coffee_70_hot_cups_sentence(catalog):
    """Covers: AC-1 (right), EC-1. Coffee, 70 guests: Hot cups, 120, 'for 70 guests', '50 extras'; no gal,
    no raw 'hot-cups', no 'Coffee: ' drink sentence. lines stay [('hot-cups', 120)]."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")], guests=70)
    assert r.status == "ok"
    assert pairs(r) == [("hot-cups", 120)]
    for part in ("Hot cups", "120", "for 70 guests", "50 extras"):
        assert part in r.text, (part, r.text)
    assert "gal" not in r.text.lower()
    assert "hot-cups" not in r.text
    assert "Coffee: " not in r.text
    assert_no_drink_amounts(r.text)


def test_cups_reason_reads_guests_plus_extras(catalog):
    """Covers: AC-1 (right), EC-1. The reason is 'N guests plus M extras' with M = count - N."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")], guests=70)
    assert "70 guests plus 50 extras" in r.text


def test_cups_text_uses_run_bev_tool_the_same_way(catalog):
    """Covers: AC-1 (right), EC-1. run_bev_tool on raw args gives the same plain cups text."""
    r = run_bev_tool({"item": "cups", "drinks": ["coffee"], "guests": 70}, catalog)
    assert r.status == "ok"
    assert "Hot cups" in r.text and "120" in r.text and "50 extras" in r.text
    assert_no_drink_amounts(r.text)


def test_cups_text_ignores_given_gallon_amounts(catalog):
    """Covers: AC-1 (boundary), EC-1. Even when the user gave gallons for the drink, a cups reply
    carries no drink amount."""
    r = run_bev_tool({"item": "cups", "drinks": ["coffee"], "gallons": [5], "guests": 70}, catalog)
    assert r.status == "ok"
    assert "Hot cups" in r.text
    assert_no_drink_amounts(r.text)


# ---------------------------------------------------------------- EC-2: two cup lines, in order

def test_ec2_coffee_and_iced_tea_two_sentences_in_order(catalog):
    """Covers: AC-1 (right), EC-2. Hot cups then Cold cups, each with 120, '70 guests', '50 extras'; no gal."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee"), DrinkRequest("Iced tea")], guests=70)
    assert r.status == "ok"
    assert r.text.index("Hot cups") < r.text.index("Cold cups")
    assert r.text.count("120") == 2
    assert r.text.count("70 guests") >= 2
    assert r.text.count("50 extras") == 2
    assert "gal" not in r.text.lower()
    assert_no_drink_amounts(r.text)


def test_cup_sentences_follow_lines_order(catalog):
    """Covers: AC-1 (boundary), EC-2. Sentences come in `lines` order: with drinks requested cold first
    the order is whatever `lines` gives."""
    r = calc(catalog, "cups", [DrinkRequest("Lemonade"), DrinkRequest("Coffee")], guests=70)
    order = [("Hot cups", r.text.index("Hot cups")), ("Cold cups", r.text.index("Cold cups"))]
    text_order = [n for n, _ in sorted(order, key=lambda p: p[1])]
    expected = ["Hot cups" if s == "hot-cups" else "Cold cups" for s, _ in pairs(r)]
    assert text_order == expected


# ---------------------------------------------------------------- EC-3: shared cold line

def test_ec3_iced_tea_and_lemonade_one_cold_sentence(catalog):
    """Covers: AC-1 (right), EC-3. One Cold cups sentence with 140, 'for 90 guests', '50 extras'; no gal;
    no Hot cups; no drink gallon sentences."""
    r = calc(catalog, "cups", [DrinkRequest("Iced tea"), DrinkRequest("Lemonade")], guests=90)
    assert r.status == "ok"
    assert pairs(r) == [("cold-cups", 140)]
    assert r.text.count("Cold cups") == 1
    assert "Hot cups" not in r.text
    for part in ("140", "for 90 guests", "50 extras"):
        assert part in r.text, (part, r.text)
    assert_no_drink_amounts(r.text)


# ---------------------------------------------------------------- EC-4 / EC-8: no drinks

def test_ec4_no_drinks_45_guests(catalog):
    """Covers: AC-1 (right), EC-4. '65', '45 guests', '20 extras', and the same count applies to hot cups
    and to cold cups. cups_each stays 65."""
    r = calc(catalog, "cups", guests=45)
    assert r.status == "ok"
    assert r.cups_each == 65
    assert r.lines == ()
    for part in ("65", "45 guests", "20 extras"):
        assert part in r.text, (part, r.text)
    low = r.text.lower()
    assert "same" in low and "hot cups" in low and "cold cups" in low
    assert_no_drink_amounts(r.text)


def test_ec8_no_drinks_one_guest_is_singular(catalog):
    """Covers: AC-1 (boundary), EC-8. 'For 1 guest' (never '1 guests'), '11', '10 extras'."""
    r = calc(catalog, "cups", guests=1)
    assert r.status == "ok"
    assert r.cups_each == 11
    assert "For 1 guest" in r.text
    assert "1 guests" not in r.text
    assert "11" in r.text and "10 extras" in r.text


@pytest.mark.parametrize(
    "guests, count, extras",
    [(20, 30, 10), (21, 41, 20), (50, 70, 20), (51, 101, 50), (100, 150, 50), (101, 201, 100), (150, 250, 100)],
)
def test_no_drinks_counts_at_extras_band_edges(catalog, guests, count, extras):
    """Covers: AC-1 (boundary), EC-4. The count, guests and extras follow the rule bands at every edge."""
    r = calc(catalog, "cups", guests=guests)
    assert r.cups_each == count
    assert str(count) in r.text
    assert f"{guests} guests" in r.text
    assert f"{extras} extras" in r.text


@pytest.mark.parametrize(
    "guests, count, extras",
    [(1, 11, 10), (20, 30, 10), (21, 41, 20), (50, 70, 20), (51, 101, 50), (100, 150, 50), (101, 201, 100)],
)
def test_cup_line_sentence_counts_at_extras_band_edges(catalog, guests, count, extras):
    """Covers: AC-1 (boundary), EC-1. With a drink named, the sentence has count, 'for N guests' and
    'M extras' at every extras band edge; 1 guest is singular."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")], guests=guests)
    assert pairs(r) == [("hot-cups", count)]
    noun = "guest" if guests == 1 else "guests"
    assert str(count) in r.text
    assert f"for {guests} {noun}" in r.text
    assert f"{extras} extras" in r.text
    assert not re.search(r"(?<!\d)1 guests", r.text), r.text
    assert_no_drink_amounts(r.text)


# ---------------------------------------------------------------- EC-5: not on the menu stays, after cups

def test_ec5_unknown_drink_sentence_kept_after_cups(catalog):
    """Covers: AC-1 (right), EC-5. Coffee + 'hot chocolate': the Hot cups sentence, then
    'hot chocolate is not on the beverage menu'; not_on_menu == ('hot chocolate',); no gal."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee"), DrinkRequest("hot chocolate")], guests=70)
    assert r.status == "ok"
    assert r.not_on_menu == ("hot chocolate",)
    low = r.text.lower()
    assert "hot cups" in low and "hot chocolate is not on the beverage menu" in low
    assert low.index("hot cups") < low.index("hot chocolate is not on the beverage menu")
    assert "gal" not in low


# ---------------------------------------------------------------- EC-6: package

def test_ec6_package_120_guests(catalog):
    """Covers: AC-1 (right), EC-6. The package at 120 guests: Hot cups and Cold cups sentences, each with
    220, 'for 120 guests' and '100 extras'; no gal."""
    r = calc(catalog, "cups", [DrinkRequest(PKG)], guests=120)
    assert r.status == "ok"
    assert dict(pairs(r)) == {"hot-cups": 220, "cold-cups": 220}
    assert "Hot cups" in r.text and "Cold cups" in r.text
    assert r.text.count("220") == 2
    assert r.text.count("for 120 guests") == 2
    assert r.text.count("100 extras") == 2
    assert_no_drink_amounts(r.text)


# ---------------------------------------------------------------- EC-7: no cups needed

def test_ec7_oatmilk_needs_no_cups(catalog):
    """Covers: AC-1 (right), EC-7. Oatmilk, 30 guests: status ok, lines (), text names Oatmilk and says no cups."""
    r = calc(catalog, "cups", [DrinkRequest("Oatmilk")], guests=30)
    assert r.status == "ok"
    assert r.lines == ()
    assert "Oatmilk" in r.text
    assert "no cups" in r.text.lower()
    assert "Hot cups" not in r.text and "Cold cups" not in r.text
    assert_no_drink_amounts(r.text)


def test_oatmilk_with_unknown_drink_keeps_not_on_menu_sentence(catalog):
    """Covers: AC-1 (boundary), EC-7, EC-5. A no-cups drink next to an unknown one: both sentences present."""
    r = calc(catalog, "cups", [DrinkRequest("Oatmilk"), DrinkRequest("hot chocolate")], guests=30)
    assert r.status == "ok"
    assert "no cups" in r.text.lower()
    assert "hot chocolate is not on the beverage menu" in r.text.lower()


def test_no_cups_sentence_not_used_when_cups_are_needed(catalog):
    """Covers: AC-1 (wrong), EC-7. A drink that needs cups does not get the 'no cups' sentence."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")], guests=70)
    assert "no cups" not in r.text.lower()


# ---------------------------------------------------------------- EC-11: run_bev_tool text

def test_ec11_run_bev_tool_text_for_iced_tea_and_lemonade(catalog):
    """Covers: AC-1 (right), EC-11. run_bev_tool's text for iced tea + lemonade at 90 guests names the cold cups."""
    args = {"item": "cups", "drinks": ["iced tea", "lemonade"], "guests": 90}
    out = run_bev_tool(args, catalog).text
    assert "Cold cups" in out and "140" in out
    assert "gal" not in out.lower()


# ---------------------------------------------------------------- EC-9 / AC-2: other statuses unchanged

def test_ec9_cups_with_drinks_but_no_guests_needs_info(catalog):
    """Covers: AC-2 (right), EC-9. need_info, a question ending in '?' that asks for guests; no cups sentence."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee")])
    assert r.status == "need_info"
    assert r.text.strip().endswith("?")
    assert "guests" in r.text.lower()
    assert "Hot cups" not in r.text
    assert r.lines == ()


def test_ec9_cups_only_unknown_drinks_is_not_on_menu(catalog):
    """Covers: AC-2 (right), EC-9. Only unknown drinks: not_on_menu, text says 'not on the beverage menu',
    and has no cups sentence."""
    r = calc(catalog, "cups", [DrinkRequest("Hot chocolate")], guests=70)
    assert r.status == "not_on_menu"
    assert r.not_on_menu == ("Hot chocolate",)
    assert "not on the beverage menu" in r.text.lower()
    assert "Hot cups" not in r.text and "Cold cups" not in r.text
    assert r.lines == ()


@pytest.mark.parametrize(
    "drinks, guests",
    [([DrinkRequest("Coffee")], 0), ([DrinkRequest("Coffee")], -5), ([DrinkRequest("Coffee")], 2.5), ((), 0)],
)
def test_ec9_cups_bad_arguments_stay_invalid(catalog, drinks, guests):
    """Covers: AC-2 (wrong), EC-9. Bad guests for cups: invalid, text starts with 'invalid', no cups sentence."""
    r = calc(catalog, "cups", drinks, guests=guests)
    assert r.status == "invalid"
    assert r.text.strip().lower().startswith("invalid")
    assert "Hot cups" not in r.text


def test_ec9_cups_bad_raw_arguments_stay_invalid(catalog):
    """Covers: AC-2 (wrong), EC-9. run_bev_tool with a bad shape for cups: invalid, with the format example."""
    r = run_bev_tool({"item": "cups", "drinks": 5, "guests": 70}, catalog)
    assert r.status == "invalid"
    for key in ('"item"', '"drinks"', '"gallons"', '"guests"'):
        assert key in r.text


# ---------------------------------------------------------------- AC-2: other BevResult fields unchanged

def test_cups_other_fields_unchanged_with_drinks(catalog):
    """Covers: AC-2 (right), EC-1. Only text changes: drinks (with amounts from guests), lines, not_on_menu,
    gallons_each and cups_each keep their values."""
    r = calc(catalog, "cups", [DrinkRequest("Coffee"), DrinkRequest("Lemonade")], guests=70)
    assert [(d.drink, d.amount, d.unit, d.from_guests) for d in r.drinks] == [
        ("Coffee", Fraction(3), "gallon", True),
        ("Lemonade", Fraction(3), "gallon", True),
    ]
    assert dict(pairs(r)) == {"hot-cups": 120, "cold-cups": 120}
    assert r.not_on_menu == ()
    assert r.gallons_each is None
    assert r.cups_each is None


def test_cups_other_fields_unchanged_without_drinks(catalog):
    """Covers: AC-2 (right), EC-4. No drinks: drinks (), lines (), gallons_each None, cups_each = count."""
    r = calc(catalog, "cups", guests=70)
    assert r.drinks == () and r.lines == ()
    assert r.gallons_each is None
    assert r.cups_each == 120


# ---------------------------------------------------------------- EC-10 / AC-2: other items keep their text

def test_ec10_gallons_text_unchanged(catalog):
    """Covers: AC-2 (right), EC-10. gallons keeps its drink amounts: 'Coffee: 3 gal from 75 guests'."""
    r = calc(catalog, "gallons", [DrinkRequest("Coffee")], guests=75)
    assert "Coffee: 3 gal" in r.text
    assert "from 75 guests" in r.text


def test_ec10_gallons_each_text_unchanged(catalog):
    """Covers: AC-2 (right), EC-10. gallons with no drinks keeps gallons and the guest count."""
    r = calc(catalog, "gallons", guests=25)
    assert "1 gallon" in r.text and "1 gallons" not in r.text
    assert "25" in r.text


def test_ec10_cambros_text_unchanged(catalog):
    """Covers: AC-2 (right), EC-10. cambros keeps 'Lemonade: 7 gal' and the cambro lines."""
    r = calc(catalog, "cambros", [DrinkRequest("Lemonade", 7, "gallons")])
    assert "Lemonade: 7 gal" in r.text
    assert "5 gal cambro: 1" in r.text and "2 gal cambro: 1" in r.text


def test_ec10_supplies_text_unchanged(catalog):
    """Covers: AC-2 (right), EC-10. supplies keeps the supply lines and ticks, and the cups-need-guests note."""
    r = calc(catalog, "supplies", [DrinkRequest("Coffee")])
    for name in ("Cocktail napkins", "Creamer", "Stir sticks", "Sugar"):
        assert name in r.text
    assert "bring" in r.text.lower()
    assert "guests" in r.text.lower()


def test_ec10_everything_keeps_raw_cup_lines(catalog):
    """Covers: AC-2 (right), EC-10. everything still has the raw 'hot-cups: 70' line the pull sheet uses,
    and the drink amount 'Coffee: 2 gal from 50 guests'."""
    r = calc(catalog, "everything", [DrinkRequest("Coffee")], guests=50)
    assert "hot-cups: 70" in r.text
    assert "Coffee: 2 gal" in r.text
    assert "2 gal cambro: 1" in r.text


def test_ec10_everything_two_cup_kinds_keep_raw_lines(catalog):
    """Covers: AC-2 (boundary), EC-10. everything with hot and cold drinks keeps both raw cup lines."""
    r = calc(catalog, "everything", [DrinkRequest("Coffee"), DrinkRequest("Lemonade")], guests=70)
    assert "hot-cups: 120" in r.text and "cold-cups: 120" in r.text


@pytest.mark.parametrize("item", ["gallons", "cambros", "supplies", "everything"])
def test_other_items_never_use_the_plain_cup_sentences(catalog, item):
    """Covers: AC-2 (wrong), EC-10. The plain 'Hot cups ... extras' wording is only for item cups."""
    r = calc(catalog, item, [DrinkRequest("Coffee", 5, "gal")], guests=70)
    assert r.status == "ok"
    assert "Hot cups" not in r.text and "Cold cups" not in r.text


def test_other_items_lines_unchanged(catalog):
    """Covers: AC-2 (right), EC-10. lines for cambros and everything are unchanged by this spec."""
    r = calc(catalog, "everything", [DrinkRequest("Coffee")], guests=50)
    assert ("2 gal cambro", 1) in pairs(r) and ("hot-cups", 70) in pairs(r)
    c = calc(catalog, "cambros", [DrinkRequest("Lemonade", 7, "gallons")])
    assert pairs(c) == [("5 gal cambro", 1), ("2 gal cambro", 1)]

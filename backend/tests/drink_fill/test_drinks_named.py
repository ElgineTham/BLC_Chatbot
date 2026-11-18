"""Spec 022, AC-2 (drinks_named): EC-3 to EC-10 and the §4.1 rules. Unit tests with N = menu_names(Appendix A)."""
from __future__ import annotations

import pytest

from blc.flow import drinks_named


@pytest.mark.parametrize("text,expected", [
    ("How many cups to bring for decaf, 40 guests", ("Decaf",)),
    ("Cups needed for orange juice and decaf, 140 guests?", ("Orange juice", "Decaf")),
])
def test_ec3_ec4_named_drinks(names, text, expected):
    """Covers: AC-2 (right), EC-3, EC-4. Display names in order of appearance (the second example is not menu order)."""
    assert drinks_named(text, names) == expected


def test_returns_a_tuple(names):
    """Covers: AC-2 (right). The result is a tuple, also when empty."""
    assert isinstance(drinks_named("decaf", names), tuple)
    assert isinstance(drinks_named("nothing here", names), tuple)


@pytest.mark.parametrize("text,expected", [
    ("DECAF for 40", ("Decaf",)),
    ("DeCaF", ("Decaf",)),
    ("Iced\n  tea for 30", ("Iced tea",)),
    ("iced\ttea", ("Iced tea",)),
    ("iced \t\n tea", ("Iced tea",)),
    ("Orange   juice", ("Orange juice",)),
])
def test_ec5_case_and_whitespace(names, text, expected):
    """Covers: AC-2 (right + boundary), EC-5. Case is ignored; a run of spaces, tabs or newlines matches one space."""
    assert drinks_named(text, names) == expected


@pytest.mark.parametrize("text", ["decaffeinated please", "the coffeemaker is broken", "xdecaf", "decafs",
                                  "Decafe", "icedtea", "lemonades"])
def test_ec6_not_whole_words(names, text):
    """Covers: AC-2 (wrong), EC-6. A name preceded or followed by a letter does not match; plurals and misspellings neither."""
    assert drinks_named(text, names) == ()


@pytest.mark.parametrize("text", ["(decaf)", "decaf?", "decaf,", "40 decaf", "decaf40", "40decaf", "-decaf-",
                                  "\"decaf\"", "decaf!"])
def test_ec6_punctuation_and_digits_around_a_name_are_fine(names, text):
    """Covers: AC-2 (right + boundary), EC-6. Punctuation, digits and spaces around a name do not stop a match."""
    assert drinks_named(text, names) == ("Decaf",)


def test_name_at_the_very_start_and_end(names):
    """Covers: AC-2 (boundary). A name that is the whole text, or at either edge, matches."""
    assert drinks_named("decaf", names) == ("Decaf",)
    assert drinks_named("decaf and lemonade", names) == ("Decaf", "Lemonade")
    assert drinks_named("lemonade and decaf", names) == ("Lemonade", "Decaf")


def test_ec7_longest_name_wins_alias(names):
    """Covers: AC-2 (right), EC-7. 'iced tea with lemon wedges' names Iced tea once."""
    assert drinks_named("iced tea with lemon wedges for 30", names) == ("Iced tea",)


def test_ec7_alias_and_its_shorter_name_give_one_display_name(names):
    """Covers: AC-2 (boundary), EC-7. 'fresh-brewed coffee and coffee' names Coffee once."""
    assert drinks_named("fresh-brewed coffee and coffee", names) == ("Coffee",)


def test_ec7_longer_alias_hides_shorter_names_inside_it(names):
    """Covers: AC-2 (wrong), EC-7. 'fresh-brewed decaffeinated coffee' is Decaf only: Coffee inside it is not matched."""
    assert drinks_named("fresh-brewed decaffeinated coffee for 40", names) == ("Decaf",)


def test_ec7_long_hot_water_alias(names):
    """Covers: AC-2 (right), EC-7. The long hot water alias gives Hot water, nothing else (no 'tea' or other drink)."""
    text = "hot water with an assortment of black, green, and herbal tea bags"
    assert drinks_named(text, names) == ("Hot water",)


def test_ec8_package_name_only_names_the_package(names, PKG):
    """Covers: AC-2 (right), EC-8. The package name hides the Coffee, Decaf and Iced water inside it."""
    text = "the Coffee, decaf, tea, iced water & juice package for 120"
    assert drinks_named(text, names) == (PKG,)


def test_ec8_package_and_separate_drink(names, PKG):
    """Covers: AC-2 (boundary), EC-8. A drink named outside the package is still found, in order."""
    text = "lemonade plus the coffee, decaf, tea, iced water & juice package"
    assert drinks_named(text, names) == ("Lemonade", PKG)


@pytest.mark.parametrize("text", ["How many hot cups for 40 guests?", "tea for 30", "juice", "hot tea", "", "   ",
                                  "How many cups for 45 guests?"])
def test_ec9_no_drink_named(names, text):
    """Covers: AC-2 (wrong + boundary), EC-9. No menu name: empty tuple; short names and the empty string too."""
    assert drinks_named(text, names) == ()


def test_ec10_order_of_first_appearance_without_repeats(names):
    """Covers: AC-2 (right), EC-10. Each display name once, in order of first appearance."""
    assert drinks_named("peach tea then lemonade then peach tea", names) == ("Peach tea", "Lemonade")


def test_three_drinks_in_text_order(names):
    """Covers: AC-2 (right), EC-4. Order follows the text, not the menu or the key order."""
    assert drinks_named("oatmilk, lemonade and coffee", names) == ("Oatmilk", "Lemonade", "Coffee")


def test_alias_and_item_of_one_drink_repeat_once(names):
    """Covers: AC-2 (boundary), EC-10. An alias then the item name gives the display name once, at first appearance."""
    assert drinks_named("decaf, then fresh-brewed decaffeinated coffee", names) == ("Decaf",)


def test_empty_names_mapping(names):
    """Covers: AC-2 (boundary). With no names nothing is named; never raises."""
    assert drinks_named("decaf and coffee", {}) == ()


def test_overlapping_names_in_a_custom_mapping():
    """Covers: AC-2 (boundary), EC-7. With a hand-made names mapping, the longest name at a place wins."""
    custom = {"tea": "Tea", "iced tea": "Iced tea", "iced tea with lemon": "Lemon iced tea"}
    assert drinks_named("iced tea with lemon", custom) == ("Lemon iced tea",)
    assert drinks_named("iced tea", custom) == ("Iced tea",)
    assert drinks_named("tea, then iced tea", custom) == ("Tea", "Iced tea")

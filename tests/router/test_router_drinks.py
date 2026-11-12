"""AC-1 (spec 010): MENU_DRINKS and menu_drinks_in (EC-1). Pure unit tests."""

from __future__ import annotations

import pytest

from blc.router import MENU_DRINKS, menu_drinks_in

EXPECTED = (
    "coffee", "decaf", "hot water", "brewed hot cider", "ginger honeycrisp apple cider",
    "cider", "iced water", "iced tea", "orange juice", "lemonade", "peach tea", "oatmilk",
    "tea", "juice", "package",
)


def test_menu_drinks_is_exactly_the_contract_tuple():
    """Covers: AC-1 (right). MENU_DRINKS equals section 3.1, in the same order."""
    assert tuple(MENU_DRINKS) == EXPECTED
    assert isinstance(MENU_DRINKS, tuple)


def test_menu_drinks_entries_are_lower_case_strings():
    """Covers: AC-1 (boundary). Every entry is a non-blank lower-case string, no duplicates."""
    assert all(isinstance(d, str) and d == d.lower() and d.strip() for d in MENU_DRINKS)
    assert len(set(MENU_DRINKS)) == len(MENU_DRINKS)


@pytest.mark.parametrize("drink", EXPECTED)
def test_every_entry_is_found_alone(drink):
    """Covers: AC-1 (right), EC-1. Each entry alone gives a result that contains it."""
    assert drink in menu_drinks_in(drink)


@pytest.mark.parametrize("drink", EXPECTED)
def test_every_entry_is_found_ignoring_case(drink):
    """Covers: AC-1 (right, boundary), EC-1. Upper and title case are matched."""
    assert drink in menu_drinks_in(drink.upper())
    assert drink in menu_drinks_in(drink.title())


@pytest.mark.parametrize("drink", EXPECTED)
def test_every_entry_is_found_inside_a_sentence_with_punctuation(drink):
    """Covers: AC-1 (right), EC-1. An entry next to punctuation and other words is a whole word or phrase."""
    assert drink in menu_drinks_in(f"Do we have ({drink}), please?")


def test_plural_is_not_a_match():
    """Covers: AC-1 (wrong), EC-1. 'lemonades' does not give 'lemonade'."""
    assert "lemonade" not in menu_drinks_in("lemonades")
    assert menu_drinks_in("lemonades") == ()


@pytest.mark.parametrize("text", ["teas", "steam", "coffees", "decafs", "juices", "packages", "tealight"])
def test_partial_words_do_not_match(text):
    """Covers: AC-1 (wrong), EC-1 (extra). A drink word inside a longer word gives nothing."""
    assert menu_drinks_in(text) == ()


def test_iced_tea_gives_iced_tea_and_tea():
    """Covers: AC-1 (right), EC-1. 'iced tea' gives both entries, in MENU_DRINKS order."""
    assert menu_drinks_in("iced tea") == ("iced tea", "tea")


def test_package_text_gives_all_six_entries():
    """Covers: AC-1 (right), EC-1. The package text gives coffee, decaf, tea, iced water, juice and package."""
    got = menu_drinks_in("coffee, decaf, tea, iced water & juice package")
    assert set(got) == {"coffee", "decaf", "tea", "iced water", "juice", "package"}
    assert len(got) == 6


def test_results_follow_menu_drinks_order_not_text_order():
    """Covers: AC-1 (right), EC-1. Order is MENU_DRINKS order; the text order does not matter."""
    assert menu_drinks_in("tea then decaf then coffee") == ("coffee", "decaf", "tea")
    assert menu_drinks_in("coffee then decaf then tea") == ("coffee", "decaf", "tea")


def test_each_entry_at_most_once():
    """Covers: AC-1 (boundary), EC-1. A repeated drink appears once."""
    assert menu_drinks_in("coffee coffee COFFEE") == ("coffee",)


def test_multi_word_phrases_need_the_whole_phrase():
    """Covers: AC-1 (wrong), EC-1. 'hot' alone, 'water' alone or 'iced' alone is not a drink."""
    assert menu_drinks_in("hot") == ()
    assert menu_drinks_in("water") == ()
    assert menu_drinks_in("iced") == ()
    assert menu_drinks_in("brewed hot") == ()


def test_peach_tea_and_orange_juice_give_their_short_words_too():
    """Covers: AC-1 (right), EC-1 (extra). 'peach tea' gives peach tea and tea; 'orange juice' gives orange juice and juice."""
    assert menu_drinks_in("peach tea") == ("peach tea", "tea")
    assert menu_drinks_in("orange juice") == ("orange juice", "juice")


def test_cider_phrases_give_cider():
    """Covers: AC-1 (right), EC-1 (extra). The long cider names also give 'cider'."""
    assert menu_drinks_in("brewed hot cider") == ("brewed hot cider", "cider")
    assert menu_drinks_in("Ginger Honeycrisp apple cider") == ("ginger honeycrisp apple cider", "cider")


@pytest.mark.parametrize("text", ["", " ", "\n\t ", "How many cups for 45 guests?", "hot chocolate"])
def test_blank_or_no_match_gives_empty_tuple(text):
    """Covers: AC-1 (wrong, boundary), EC-1. Blank text or no drink gives ()."""
    assert menu_drinks_in(text) == ()


def test_returns_a_tuple_and_prints_nothing(capsys):
    """Covers: AC-1 (boundary), EC-1. The result is a tuple of strings; nothing is printed."""
    got = menu_drinks_in("Coffee and lemonade")
    assert isinstance(got, tuple)
    assert got == ("coffee", "lemonade")
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_very_long_text_does_not_raise():
    """Covers: AC-1 (boundary), EC-1 (extra). A very long text works."""
    assert menu_drinks_in("x " * 100000 + "lemonade") == ("lemonade",)

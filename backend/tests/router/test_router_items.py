"""AC-1: the beverage pull sheet item set and pull_sheet_items_in (EC-1 to EC-4). Pure unit tests."""

from __future__ import annotations

import pytest

from blc.router import PULL_SHEET_ITEMS, pull_sheet_items_in

EXPECTED = {
    "gallons": ("gallon", "gallons", "gal"),
    "cambros": ("cambro", "cambros", "jug", "jugs", "container", "containers"),
    "cups": ("cup", "cups"),
    "napkins": ("napkin", "napkins"),
    "creamer": ("creamer",),
    "stir sticks": ("stir stick", "stir sticks"),
    "sugar": ("sugar",),
    "lemon tongs": ("lemon tongs", "tongs"),
    "lemons": ("lemon", "lemons"),
    "tea packets": ("tea packet", "tea packets", "tea bag", "tea bags"),
    "everything": ("bring", "pull sheet", "pack"),
}
ORDER = list(EXPECTED)
ALL_WORDS = [(item, word) for item, words in EXPECTED.items() for word in words]


# ---------------------------------------------------------------- AC-1: the constant

def test_item_set_has_exactly_the_contract_keys_and_words():
    """Covers: AC-1 (right). Keys and words equal section 3.1, in the same key order."""
    assert dict(PULL_SHEET_ITEMS) == EXPECTED
    assert list(PULL_SHEET_ITEMS) == ORDER


def test_item_words_are_lower_case_tuples():
    """Covers: AC-1 (boundary). Every value is a tuple of lower-case strings."""
    for item, words in PULL_SHEET_ITEMS.items():
        assert isinstance(words, tuple), item
        assert all(isinstance(w, str) and w == w.lower() and w.strip() for w in words), item


# ---------------------------------------------------------------- EC-1: every word

@pytest.mark.parametrize("item, word", ALL_WORDS)
def test_every_word_gives_its_item(item, word):
    """Covers: AC-1 (right), EC-1. Each word of each item gives that item."""
    assert item in pull_sheet_items_in(f"Do we need {word} today?")


@pytest.mark.parametrize("item, word", ALL_WORDS)
def test_every_word_alone_gives_its_item_ignoring_case(item, word):
    """Covers: AC-1 (right, boundary), EC-1. The bare word, in upper and title case, gives the item."""
    assert item in pull_sheet_items_in(word)
    assert item in pull_sheet_items_in(word.upper())
    assert item in pull_sheet_items_in(word.title())


def test_case_examples_from_spec():
    """Covers: AC-1 (right), EC-1. 'CAMBROS' and 'Cups' are matched."""
    assert pull_sheet_items_in("CAMBROS") == ("cambros",)
    assert pull_sheet_items_in("Cups") == ("cups",)


def test_punctuation_next_to_a_word_still_matches():
    """Covers: AC-1 (boundary), EC-1. A word followed by ? , . or inside quotes is still a whole word."""
    assert pull_sheet_items_in("How many cups?") == ("cups",)
    assert pull_sheet_items_in("napkins, creamer.") == ("napkins", "creamer")
    assert pull_sheet_items_in('"sugar"') == ("sugar",)


def test_lemon_tongs_phrase_gives_lemon_tongs():
    """Covers: AC-1 (right), EC-1. The phrase 'lemon tongs' gives 'lemon tongs'."""
    assert "lemon tongs" in pull_sheet_items_in("Where are the lemon tongs kept?")


# ---------------------------------------------------------------- EC-2: whole words only

@pytest.mark.parametrize(
    "text, forbidden",
    [
        ("lemonade", "lemons"),
        ("cupboard", "cups"),
        ("gallonage", "gallons"),
        ("sugary", "sugar"),
        ("napkinsx", "napkins"),
        ("encontainers", "cambros"),
        ("creamery", "creamer"),
    ],
)
def test_partial_words_do_not_match(text, forbidden):
    """Covers: AC-1 (wrong), EC-2. A set word inside a longer word is not a match."""
    assert forbidden not in pull_sheet_items_in(text)


@pytest.mark.parametrize("text", ["lemonade", "cupboard", "gallonage"])
def test_spec_partial_examples_give_nothing(text):
    """Covers: AC-1 (wrong), EC-2. The three spec examples give no item at all."""
    assert pull_sheet_items_in(text) == ()


def test_package_is_not_pack():
    """Covers: AC-1 (wrong), EC-2 (extra). 'package' is not the word 'pack', so 'everything' is not given."""
    assert "everything" not in pull_sheet_items_in("What is in the orange juice package?")


def test_a_phrase_is_not_matched_across_a_different_word():
    """Covers: AC-1 (wrong), EC-2 (extra). 'stir' alone or 'tea' alone is not an item."""
    assert pull_sheet_items_in("Do we stir the tea?") == ()


# ---------------------------------------------------------------- EC-3: order and uniqueness

def test_several_items_come_back_in_set_order():
    """Covers: AC-1 (right), EC-3. The spec example comes back in PULL_SHEET_ITEMS order."""
    assert pull_sheet_items_in("Do I bring sugar for 5 gal and cups?") == ("gallons", "cups", "sugar", "everything")


def test_order_does_not_depend_on_text_order():
    """Covers: AC-1 (right), EC-3. Reversing the text does not change the result."""
    a = pull_sheet_items_in("lemons then napkins then cups then gallons")
    b = pull_sheet_items_in("gallons then cups then napkins then lemons")
    assert a == b == ("gallons", "cups", "napkins", "lemons")


def test_each_item_at_most_once():
    """Covers: AC-1 (boundary), EC-3. Repeated and mixed words of one item give it once."""
    assert pull_sheet_items_in("cup cups CUP Cups") == ("cups",)
    assert pull_sheet_items_in("gal gallon gallons") == ("gallons",)


def test_result_is_a_tuple():
    """Covers: AC-1 (right). The return type is a tuple, also when empty."""
    assert isinstance(pull_sheet_items_in("cups"), tuple)
    assert isinstance(pull_sheet_items_in(""), tuple)


# ---------------------------------------------------------------- EC-4: nothing

@pytest.mark.parametrize("text", ["", " ", "   \n\t ", "Where is the mint kept?", "How is the weather?"])
def test_no_item_gives_empty_tuple(text):
    """Covers: AC-1 (wrong, boundary), EC-4. Empty, whitespace and no-item text give ()."""
    assert pull_sheet_items_in(text) == ()


def test_prints_nothing_and_never_raises(capsys):
    """Covers: AC-1 (boundary), spec 3.1 'Prints nothing, never raises'. Odd text is handled quietly."""
    for text in ("", "\x00", "((( [[[ ***", "ünïcödé cups", "a" * 10000):
        pull_sheet_items_in(text)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""

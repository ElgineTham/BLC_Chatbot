"""Spec 021, AC-1 (number check, EC-1 to EC-12) and NFR-1 (EC-4, EC-5, EC-12 behaviour).

Unit tests of the pure function blc.flow.invented_numbers. No models, no data files.
"""
from __future__ import annotations

import pytest

from blc.flow import CHECKED_ARGUMENTS, invented_numbers

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"


def bev(**kw):
    return {"item": "cambros", "drinks": ["peach tea"], **kw}


# ---------------------------------------------------------------- constants

def test_checked_arguments_constant():
    """Covers: AC-1 (right). CHECKED_ARGUMENTS is exactly ("guests", "gallons")."""
    assert CHECKED_ARGUMENTS == ("guests", "gallons")


# ---------------------------------------------------------------- EC-1, EC-2

def test_ec1_invented_gallons_reported():
    """Covers: AC-1 (wrong), EC-1. gallons [6] for '60 guests' is invented; guests 60 is fine."""
    q = "For 60 guests of peach tea, how many cambros and cups"
    assert invented_numbers(BEV, bev(guests=60, gallons=[6]), q) == {"gallons": (6,)}


def test_ec2_no_gallons_nothing_invented():
    """Covers: AC-1 (right), EC-2. The same call without gallons returns {}."""
    q = "For 60 guests of peach tea, how many cambros and cups"
    assert invented_numbers(BEV, bev(guests=60), q) == {}


def test_result_is_a_dict_of_tuples():
    """Covers: AC-1 (right), EC-1. The invented values come as a tuple."""
    r = invented_numbers(BEV, bev(guests=60, gallons=[6]), "For 60 guests of peach tea")
    assert isinstance(r, dict)
    assert isinstance(r["gallons"], tuple)


def test_invented_guests_reported():
    """Covers: AC-1 (wrong), EC-1. An invented guests value is reported under 'guests'."""
    assert invented_numbers(BEV, bev(guests=70), "How many cambros for 7 gallons of peach tea") == {"guests": (70,)}


def test_both_arguments_invented_reported_together():
    """Covers: AC-1 (wrong), extra. Both guests and gallons invented gives both keys."""
    r = invented_numbers(BEV, bev(guests=33, gallons=[44]), "How many cambros of peach tea")
    assert r == {"guests": (33,), "gallons": (44,)}


# ---------------------------------------------------------------- EC-3

def test_ec3_all_gallons_given():
    """Covers: AC-1 (right), EC-3. [7, 3] against '7 gallons ... and 3 gallons' is fine."""
    q = "7 gallons of peach tea and 3 gallons of hot water"
    args = {"item": "cambros", "drinks": ["peach tea", "hot water"], "gallons": [7, 3]}
    assert invented_numbers(BEV, args, q) == {}


def test_ec3_one_of_two_invented():
    """Covers: AC-1 (wrong), EC-3. [7, 4] reports only the 4."""
    q = "7 gallons of peach tea and 3 gallons of hot water"
    args = {"item": "cambros", "drinks": ["peach tea", "hot water"], "gallons": [7, 4]}
    assert invented_numbers(BEV, args, q) == {"gallons": (4,)}


def test_several_invented_values_in_order():
    """Covers: AC-1 (wrong), EC-3. Invented values come in the order of the list."""
    args = {"item": "cambros", "drinks": ["a", "b", "c"], "gallons": [9, 3, 8]}
    assert invented_numbers(BEV, args, "3 gallons of each") == {"gallons": (9, 8)}


def test_single_gallons_value_not_a_list_is_checked():
    """Covers: AC-1 (wrong), EC-3. A single gallons value is checked like a list item."""
    assert invented_numbers(BEV, bev(gallons=8), "How many cambros for 5 gallons") == {"gallons": (8,)}
    assert invented_numbers(BEV, bev(gallons=5), "How many cambros for 5 gallons") == {}


# ---------------------------------------------------------------- EC-4

@pytest.mark.parametrize("question, guests", [
    ("cambros for twenty-five guests of hot water", 25),
    ("cambros for forty five guests of hot water", 45),
    ("cambros for one hundred guests of hot water", 100),
    ("cambros for thirty guests of hot water", 30),
    ("cambros for twelve guests of hot water", 12),
])
def test_ec4_number_words_allowed(question, guests):
    """Covers: AC-1 (right), EC-4, NFR-1. Hyphenated, spaced and plain number words are numbers."""
    assert invented_numbers(BEV, bev(guests=guests), question) == {}


@pytest.mark.parametrize("question, guests", [
    ("cambros for twenty-five guests of hot water", 26),
    ("cambros for forty five guests of hot water", 40),
    ("cambros for one hundred guests of hot water", 101),
])
def test_ec4_number_words_do_not_allow_neighbours(question, guests):
    """Covers: AC-1 (wrong), EC-4, NFR-1. A different number than the word's is invented."""
    assert invented_numbers(BEV, bev(guests=guests), question) == {"guests": (guests,)}


# ---------------------------------------------------------------- EC-5

def test_ec5_decimal_allowed():
    """Covers: AC-1 (right), EC-5, NFR-1. 2.5 is a number."""
    assert invented_numbers(REC, {"recipe": "lemonade", "gallons": 2.5}, "2.5 gallons of lemonade") == {}


def test_ec5_decimal_not_glued_into_25():
    """Covers: AC-1 (wrong), EC-5, NFR-1. 25 is invented when the text only has 2.5."""
    r = invented_numbers(REC, {"recipe": "lemonade", "gallons": 25}, "2.5 gallons of lemonade")
    assert r == {"gallons": (25,)}


def test_ec5_thousands_separator_allowed():
    """Covers: AC-1 (right), EC-5, NFR-1. '1,200 guests' allows 1200."""
    assert invented_numbers(BEV, bev(guests=1200), "cambros for 1,200 guests") == {}


def test_ec5_thousands_separator_does_not_allow_pieces():
    """Covers: AC-1 (wrong), EC-5, NFR-1. '1,200' is one number, not 1 and 200."""
    assert invented_numbers(BEV, bev(guests=200), "cambros for 1,200 guests") == {"guests": (200,)}


# ---------------------------------------------------------------- EC-6

def test_ec6_one_always_allowed():
    """Covers: AC-1 (right), EC-6. 'a gallon of decaf' allows gallons [1]."""
    assert invented_numbers(BEV, bev(gallons=[1]), "a gallon of decaf") == {}


def test_ec6_guests_one_allowed_too():
    """Covers: AC-1 (boundary), EC-6. The number 1 is allowed for guests as well."""
    assert invented_numbers(BEV, bev(guests=1), "cups for one guest") == {}


def test_ec6_two_not_allowed_by_a_gallon():
    """Covers: AC-1 (boundary), EC-6. Only 1 is free: gallons [2] is invented for 'a gallon of decaf'."""
    assert invented_numbers(BEV, bev(gallons=[2]), "a gallon of decaf") == {"gallons": (2,)}


# ---------------------------------------------------------------- EC-7

_HIST = [
    {"role": "user", "content": "How many gallons of coffee for 100 guests?"},
    {"role": "assistant", "content": "Coffee: 4 gallons for 100 guests."},
]


def test_ec7_assistant_reply_number_allowed():
    """Covers: AC-1 (right), EC-7. gallons [4] comes from the assistant's reply."""
    assert invented_numbers(BEV, bev(gallons=[4]), "How many cambros for that?", _HIST) == {}


def test_ec7_user_history_number_allowed():
    """Covers: AC-1 (right), EC-7. guests 100 comes from the earlier user message."""
    assert invented_numbers(BEV, bev(guests=100), "How many cambros for that?", _HIST) == {}


def test_ec7_number_not_in_history_invented():
    """Covers: AC-1 (wrong), EC-7. gallons [5] is in neither the question nor the history."""
    r = invented_numbers(BEV, bev(gallons=[5]), "How many cambros for that?", _HIST)
    assert r == {"gallons": (5,)}


def test_ec7_summary_item_counts():
    """Covers: AC-1 (right), EC-7. A summary item's numbers are allowed."""
    hist = [{"role": "summary", "content": "Earlier: 12 gallons of lemonade were planned."}]
    assert invented_numbers(BEV, bev(gallons=[12]), "How many cambros for that?", hist) == {}


def test_history_none_and_empty_behave_the_same():
    """Covers: AC-1 (boundary), EC-7. history None and [] both mean no history."""
    q = "cambros for 6 gallons"
    assert invented_numbers(BEV, bev(gallons=[7]), q, None) == invented_numbers(BEV, bev(gallons=[7]), q, [])
    assert invented_numbers(BEV, bev(gallons=[7]), q, []) == {"gallons": (7,)}


# ---------------------------------------------------------------- EC-8

def test_ec8_numeric_string_given_is_fine():
    """Covers: AC-1 (right), EC-8. guests '60' against '60 guests' returns {}."""
    assert invented_numbers(BEV, bev(guests="60"), "cambros for 60 guests") == {}


def test_ec8_numeric_string_invented_keeps_the_string():
    """Covers: AC-1 (wrong), EC-8. guests '6' is invented and reported as the string '6'."""
    assert invented_numbers(BEV, bev(guests="6"), "cambros for 60 guests") == {"guests": ("6",)}


# ---------------------------------------------------------------- EC-9

@pytest.mark.parametrize("args", [
    bev(guests=True),
    bev(gallons="lots"),
    bev(gallons=None),
    bev(gallons=[]),
    bev(guests=None),
    bev(gallons=[True]),
])
def test_ec9_non_numbers_not_checked(args):
    """Covers: AC-1 (boundary), EC-9. bool, words, null and an empty list are the tool's job."""
    assert invented_numbers(BEV, args, "cambros for 60 guests") == {}


def test_ec9_non_number_next_to_a_number_does_not_hide_it():
    """Covers: AC-1 (boundary), EC-9. 'lots' is skipped, the invented 9 next to it is still reported."""
    assert invented_numbers(BEV, bev(gallons=["lots", 9]), "cambros for 60 guests") == {"gallons": (9,)}


# ---------------------------------------------------------------- EC-10

def test_ec10_recipe_invented_gallons():
    """Covers: AC-1 (wrong), EC-10. scale_recipe gallons 3 for '75 guests' is invented."""
    args = {"recipe": "lemonade", "guests": 75, "gallons": 3}
    assert invented_numbers(REC, args, "How do I make lemonade for 75 guests?") == {"gallons": (3,)}


def test_ec10_recipe_guests_checked_and_clean_call_passes():
    """Covers: AC-1 (right), EC-10. scale_recipe guests is checked too; a clean call returns {}."""
    q = "How do I make lemonade for 75 guests?"
    assert invented_numbers(REC, {"recipe": "lemonade", "guests": 75}, q) == {}
    assert invented_numbers(REC, {"recipe": "lemonade", "guests": 57}, q) == {"guests": (57,)}


def test_recipe_words_are_not_checked():
    """Covers: AC-1 (boundary), out of scope. The recipe name is a word and is never checked."""
    assert invented_numbers(REC, {"recipe": "lemonade 99"}, "How do I make lemonade?") == {}


# ---------------------------------------------------------------- EC-11

@pytest.mark.parametrize("question", ["where are the cambros", "9 cambros", "Where are the 9 cambros"])
def test_ec11_search_never_checked(question):
    """Covers: AC-1 (boundary), EC-11. search_documents with a number in its query returns {}."""
    assert invented_numbers(SEARCH, {"query": "where are the 9 cambros"}, question) == {}


def test_ec11_unknown_tool_name_never_checked():
    """Covers: AC-1 (boundary), EC-11. A tool name outside section 4.2 returns {} even with invented numbers."""
    assert invented_numbers("some_other_tool", {"guests": 99, "gallons": [88]}, "hello") == {}


# ---------------------------------------------------------------- EC-12

def test_ec12_whole_number_match_60_does_not_allow_6():
    """Covers: AC-1 (wrong), EC-12, NFR-1. '60 guests' never allows 6."""
    assert invented_numbers(BEV, bev(gallons=[6]), "60 guests") == {"gallons": (6,)}


def test_ec12_whole_number_match_16_does_not_allow_6():
    """Covers: AC-1 (wrong), EC-12, NFR-1. '16 gallons' never allows 6, nor 1 and 6 pieces beyond the free 1."""
    assert invented_numbers(BEV, bev(gallons=[6]), "16 gallons") == {"gallons": (6,)}
    assert invented_numbers(BEV, bev(gallons=[16]), "16 gallons") == {}


def test_number_inside_a_longer_number_text_not_allowed():
    """Covers: AC-1 (boundary), EC-12. '160' does not allow 16 or 60."""
    assert invented_numbers(BEV, bev(guests=60), "cups for 160 guests") == {"guests": (60,)}


# ---------------------------------------------------------------- never raises / pure

@pytest.mark.parametrize("args", [
    {}, {"guests": [1, 2]}, {"gallons": {"a": 1}}, {"guests": object()}, {"gallons": [[1], None, "x"]},
])
def test_never_raises_on_odd_arguments(args):
    """Covers: AC-1 (boundary), EC-9. Odd argument shapes never raise; the result is a dict."""
    assert isinstance(invented_numbers(BEV, args, "cambros for 60 guests"), dict)


def test_does_not_modify_its_inputs():
    """Covers: AC-1 (boundary). The function is pure: args and history are left as they were."""
    args = bev(guests=60, gallons=[6])
    hist = [dict(h) for h in _HIST]
    invented_numbers(BEV, args, "For 60 guests", hist)
    assert args == bev(guests=60, gallons=[6])
    assert hist == _HIST


def test_question_is_stripped_and_empty_question_allows_only_one():
    """Covers: AC-1 (boundary). An empty question has no numbers: 5 is invented, 1 is not."""
    assert invented_numbers(BEV, bev(gallons=[5]), "") == {"gallons": (5,)}
    assert invented_numbers(BEV, bev(gallons=[1]), "") == {}

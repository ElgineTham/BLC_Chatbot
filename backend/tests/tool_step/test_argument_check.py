"""Spec 009 AC-1: check_arguments (unit, no model, no I/O, nothing read under data/)."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from blc.tool_step import REJECTED_PREFIX, check_arguments


def _assert_refused(reason, *needles):
    assert isinstance(reason, str), f"expected a refusal, got {reason!r}"
    assert reason.startswith(REJECTED_PREFIX)
    assert "\n" not in reason
    low = reason.lower()
    for n in needles:
        assert n.lower() in low, f"{n!r} not in {reason!r}"


MOCHA = "How many cups do I need for the mocha?"
DECAF85 = "What do I need to bring for decaf for 85 guests?"
CAMBROS12 = "Which cambros for 12 gallons of decaf?"


def test_prefix_value():
    """Covers: AC-1 (right), EC-7. REJECTED_PREFIX is exactly 'invalid (check): '."""
    assert REJECTED_PREFIX == "invalid (check): "


# ---- EC-1: every row of section 4.2 -------------------------------------------------------

def test_table_invented_guests_refused():
    """Covers: AC-1 (wrong), EC-1. Row 1: guests 50 not in the question."""
    r = check_arguments({"item": "cups", "drinks": ["coffee"], "guests": 50}, MOCHA)
    _assert_refused(r, "guests", "50")


def test_table_no_guests_ok():
    """Covers: AC-1 (right), EC-1. Row 2."""
    assert check_arguments({"item": "cups", "drinks": ["coffee"]}, MOCHA) is None


def test_table_supplies_instead_of_everything_refused():
    """Covers: AC-1 (wrong), EC-1. Row 3: rule B."""
    r = check_arguments({"item": "supplies", "drinks": ["decaf"], "guests": 85}, DECAF85)
    _assert_refused(r, "item", "everything")


def test_table_everything_ok():
    """Covers: AC-1 (right), EC-1. Row 4."""
    assert check_arguments({"item": "everything", "drinks": ["decaf"], "guests": 85}, DECAF85) is None


def test_table_sugar_is_another_item():
    """Covers: AC-1 (right), EC-1, EC-8. Row 5: sugar is another item, rule B does not apply."""
    q = "Do I bring sugar for the chai station?"
    assert check_arguments({"item": "supplies", "drinks": ["hot water"]}, q) is None


def test_table_gallons_ok():
    """Covers: AC-1 (right), EC-1. Row 6."""
    args = {"item": "cambros", "drinks": ["decaf"], "gallons": [12]}
    assert check_arguments(args, CAMBROS12) is None


def test_table_split_gallons_refused():
    """Covers: AC-1 (wrong), EC-1, EC-4. Row 7: [10, 2] names 10."""
    args = {"item": "cambros", "drinks": ["decaf"], "gallons": [10, 2]}
    _assert_refused(check_arguments(args, CAMBROS12), "gallons", "10")


def test_table_worked_out_gallons_refused():
    """Covers: AC-1 (wrong), EC-1. Row 8: gallons worked out from guests."""
    args = {"item": "cambros", "drinks": ["decaf"], "gallons": [3], "guests": 70}
    _assert_refused(check_arguments(args, "Decaf for 70 guests, which cambros?"), "gallons", "3")


def test_table_word_number_ok():
    """Covers: AC-1 (right), EC-1, EC-2. Row 9: 'Seven' as a word."""
    args = {"item": "cambros", "drinks": ["decaf"], "gallons": [7]}
    assert check_arguments(args, "Seven gallons of decaf, which containers?") is None


def test_table_gallons_item_not_everything_only():
    """Covers: AC-1 (right), EC-1, EC-8. Row 10: gallons is another item."""
    args = {"item": "cambros", "drinks": ["decaf"], "gallons": [8]}
    assert check_arguments(args, "What do I put 8 gallons of decaf in?") is None


# ---- EC-2: what counts as appearing ---------------------------------------------------------

@pytest.mark.parametrize("question,args", [
    ("We have 50 guests", {"guests": 50}),
    ("We need 2.5 gallons of decaf", {"gallons": 2.5}),
    ("We have 2.5 gallons of decaf", {"gallons": [2.5]}),
    ("An event with 1,000 guests", {"guests": 1000}),
    ("We have seven gallons of decaf", {"gallons": [7]}),
    ("We have twelve guests", {"guests": 12}),
    ("We have twenty-five guests", {"guests": 25}),
    ("We have one hundred guests", {"guests": 100}),
    ("We have SEVEN gallons of decaf", {"gallons": [7]}),
    ("We have Twenty-Five guests", {"guests": 25}),
    ("We have zero guests", {"guests": 0}),
])
def test_number_appears(question, args):
    """Covers: AC-1 (right), EC-2. Digits, decimal, comma, words and case all count as appearing."""
    assert check_arguments(args, question) is None


@pytest.mark.parametrize("question,args,needle", [
    ("A 50 guest event", {"guests": 5}, "5"),
    ("A 500 guest event", {"guests": 50}, "50"),
    ("A 125 guest event", {"guests": 25}, "25"),
    ("A 50 guest event", {"gallons": [5]}, "5"),
    ("How many cups?", {"guests": 40}, "40"),
])
def test_number_not_appearing_refused(question, args, needle):
    """Covers: AC-1 (wrong), EC-2 (boundary). A number only part of another number does not appear."""
    key = next(iter(args))
    _assert_refused(check_arguments(args, question), key, needle)


# ---- EC-3: types ----------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["50", 50.0])
def test_text_or_float_is_the_number(value):
    """Covers: AC-1 (right), EC-3. '50' and 50.0 count as 50 and are found in the question."""
    assert check_arguments({"guests": value}, "We have 50 guests") is None


def test_text_number_not_in_question_refused():
    """Covers: AC-1 (wrong), EC-3. '50' as text is still checked."""
    _assert_refused(check_arguments({"guests": "50"}, "How many cups?"), "guests", "50")


def test_float_not_in_question_refused():
    """Covers: AC-1 (wrong), EC-3. 50.0 is checked as 50."""
    _assert_refused(check_arguments({"guests": 50.0}, "How many cups?"), "guests")


@pytest.mark.parametrize("args", [
    {"guests": "seventy"}, {"guests": None}, {"guests": []}, {}, {"gallons": None},
    {"gallons": []}, {"gallons": "lots"}, {"gallons": [[9]]}, {"gallons": [5, None]},
    {"gallons": [5, "many"]}, {"gallons": [5, [9]]},
])
def test_non_numbers_ignored(args):
    """Covers: AC-1 (right), EC-3 (boundary). Non-numeric values, empty lists and missing keys are ignored."""
    assert check_arguments(args, "We have 5 gallons") is None


# ---- EC-4: lists ----------------------------------------------------------------------------

def test_list_each_number_found():
    """Covers: AC-1 (right), EC-4."""
    q = "5 gallons of one and 3 of the other"
    assert check_arguments({"gallons": [5, 3]}, q) is None


def test_list_one_number_missing_refused():
    """Covers: AC-1 (wrong), EC-4. [5, 4] is refused naming 4."""
    q = "5 gallons of one and 3 of the other"
    _assert_refused(check_arguments({"gallons": [5, 4]}, q), "gallons", "4")


def test_single_number_gallons_checked():
    """Covers: AC-1 (wrong), EC-4. gallons may be a single number."""
    _assert_refused(check_arguments({"gallons": 9}, "5 gallons of decaf"), "gallons", "9")
    assert check_arguments({"gallons": 5}, "5 gallons of decaf") is None


def test_guests_and_gallons_both_checked():
    """Covers: AC-1 (wrong), EC-4. A bad value in either argument is refused."""
    q = "5 gallons of decaf for 20 guests"
    assert check_arguments({"gallons": [5], "guests": 20}, q) is None
    _assert_refused(check_arguments({"gallons": [5], "guests": 30}, q), "guests", "30")


# ---- EC-5: the number 1 ---------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    {"guests": 1}, {"gallons": [1]}, {"gallons": 1}, {"guests": "1"}, {"guests": 1.0},
])
def test_one_always_accepted(args):
    """Covers: AC-1 (right), EC-5."""
    assert check_arguments(args, "How many cups do I need?") is None


def test_ten_is_not_one():
    """Covers: AC-1 (wrong), EC-5 (boundary). 10 is not accepted just because 1 is."""
    _assert_refused(check_arguments({"guests": 10}, "How many cups for 1 gallon?"), "guests", "10")


# ---- EC-6: never raises ---------------------------------------------------------------------

WEIRD_ARGS = [
    {}, {"item": 5, "drinks": {"a": 1}}, {"item": None}, {"item": ["everything"]},
    {"guests": object()}, {"guests": {"x": 1}}, {"guests": (1, 2)}, {"guests": True},
    {"guests": float("nan")}, {"guests": float("inf")}, {"guests": -5}, {"guests": 10 ** 30},
    {"gallons": float("nan")}, {"gallons": [float("inf")]}, {"gallons": {"a": 1}},
    {"gallons": [[1], [2, [3]]]}, {"gallons": "5"}, {"extra": 1, "more": [1, 2], "guests": 50},
    {"guests": "", "gallons": ""}, {"guests": "1e3"}, {"guests": " 50 "},
    MappingProxyType({"guests": 50}),
]
QUESTIONS = ["", "   ", DECAF85, "pull sheet", "50 " * 50, "\n\n", "é ü 五十", "x" * 100_000]


@pytest.mark.parametrize("args", WEIRD_ARGS, ids=[str(i) for i in range(len(WEIRD_ARGS))])
@pytest.mark.parametrize("question", QUESTIONS, ids=["empty", "blank", "decaf", "ps", "many50", "nl", "uni", "long"])
def test_never_raises(args, question):
    """Covers: AC-1 (boundary), EC-6. Any args and question: None or a one-line prefixed string."""
    r = check_arguments(args, question)
    assert r is None or (isinstance(r, str) and r.startswith(REJECTED_PREFIX) and "\n" not in r)


def test_empty_question_refuses_numbers():
    """Covers: AC-1 (wrong), EC-6 (boundary). An empty question contains no number."""
    _assert_refused(check_arguments({"guests": 50}, ""), "guests", "50")
    assert check_arguments({}, "") is None


def test_long_question_number_at_end():
    """Covers: AC-1 (right/wrong), EC-6 (boundary). A very long question is searched fully."""
    long = "word " * 20_000
    assert check_arguments({"guests": 50}, long + "50") is None
    _assert_refused(check_arguments({"guests": 50}, long), "guests", "50")


def test_extra_keys_ignored():
    """Covers: AC-1 (right), EC-6. Other keys are not looked at."""
    args = {"item": "cups", "drinks": {"a": 1}, "colour": 77, "guests": 50}
    assert check_arguments(args, "How many cups for 50 guests?") is None


def test_input_not_mutated():
    """Covers: AC-1 (right), EC-6. check_arguments does not change args."""
    args = {"item": "cups", "guests": 50, "gallons": [3]}
    before = {"item": "cups", "guests": 50, "gallons": [3]}
    check_arguments(args, "How many cups?")
    assert args == before


# ---- EC-7: reason shape ---------------------------------------------------------------------

def test_reason_shape_with_several_problems():
    """Covers: AC-1 (wrong), EC-7. Several problems: still one string, prefix, no newline."""
    args = {"item": "supplies", "guests": 99, "gallons": [3]}
    r = check_arguments(args, DECAF85)
    _assert_refused(r)


@pytest.mark.parametrize("question,args", [
    (MOCHA, {"item": "cups", "guests": 50}),
    (DECAF85, {"item": "supplies", "guests": 85}),
    (CAMBROS12, {"item": "cambros", "gallons": [10, 2]}),
])
def test_reason_is_one_line(question, args):
    """Covers: AC-1 (wrong), EC-7."""
    r = check_arguments(args, question)
    assert r is not None and r.startswith(REJECTED_PREFIX)
    assert "\n" not in r and "\r" not in r


# ---- Rule B and EC-8 ------------------------------------------------------------------------

def test_everything_missing_item_refused():
    """Covers: AC-1 (wrong), EC-8. Everything-only question and no item: refused naming item and everything."""
    _assert_refused(check_arguments({"drinks": ["decaf"], "guests": 85}, DECAF85), "item", "everything")


@pytest.mark.parametrize("item", ["cups", "cambros", "gallons", "supplies"])
def test_everything_only_other_items_refused(item):
    """Covers: AC-1 (wrong), EC-8. Any item other than everything is refused."""
    _assert_refused(check_arguments({"item": item, "drinks": ["decaf"], "guests": 85}, DECAF85),
                    "item", "everything")


def test_pull_sheet_question_wants_everything():
    """Covers: AC-1 (wrong/right), EC-8. 'what goes on the pull sheet' is the item everything."""
    q = "What goes on the pull sheet for decaf for 85 guests?"
    _assert_refused(check_arguments({"item": "cups", "drinks": ["decaf"], "guests": 85}, q),
                    "item", "everything")
    assert check_arguments({"item": "everything", "drinks": ["decaf"], "guests": 85}, q) is None


@pytest.mark.parametrize("item", ["cups", "supplies", "everything"])
def test_pull_sheet_and_cups_not_constrained(item):
    """Covers: AC-1 (right), EC-8 (boundary). 'pull sheet' together with 'cups': rule B does not apply."""
    q = "What goes on the pull sheet for decaf, and how many cups for 85 guests?"
    assert check_arguments({"item": item, "drinks": ["decaf"], "guests": 85}, q) is None


@pytest.mark.parametrize("item", ["everything", "Everything", "EVERYTHING", "  everything  ", " Everything\t"])
def test_everything_ignores_case_and_spaces(item):
    """Covers: AC-1 (right), rule B (revision 1). 'everything' matches ignoring case and surrounding spaces."""
    assert check_arguments({"item": item, "drinks": ["decaf"], "guests": 85}, DECAF85) is None


@pytest.mark.parametrize("item", [5, None, ["everything"], {"item": "everything"}, True, "", "every thing", "everything else"])
def test_everything_non_text_or_other_text_refused(item):
    """Covers: AC-1 (wrong), rule B (revision 1). A non-text item or any other text is refused."""
    r = check_arguments({"item": item, "drinks": ["decaf"], "guests": 85}, DECAF85)
    _assert_refused(r, "item", "everything")


# ---- EC-2 / EC-14 (revision 1): whole matches only ------------------------------------------

@pytest.mark.parametrize("question,args", [
    ("Which cambros for 17 gallons of decaf?", {"gallons": [7]}),
    ("We have seventeen gallons of decaf", {"gallons": [7]}),
    ("We have often 3 guests", {"guests": 10}),
    ("A 150 guest event", {"guests": 50}),
    ("A 500 guest event", {"guests": 50}),
    ("We have seventy guests", {"guests": 7}),
    ("We have eighteen guests", {"guests": 8}),
])
def test_partial_matches_refused(question, args):
    """Covers: AC-1 (wrong), EC-2, EC-14 (boundary). A number found only inside another number or word is not found."""
    key = next(iter(args))
    assert check_arguments(args, question) is not None
    assert str(check_arguments(args, question)).startswith(REJECTED_PREFIX)
    assert key in check_arguments(args, question).lower()


@pytest.mark.parametrize("question,args", [
    ("Which cambros for 17 gallons of decaf?", {"gallons": [17]}),
    ("We often have 10 guests", {"guests": 10}),
    ("A 50-guest event", {"guests": 50}),
    ("It costs $50 per head", {"guests": 50}),
    ("We have twenty five guests", {"guests": 25}),
    ("We have Twenty Five guests", {"guests": 25}),
    ("We have seventeen guests", {"guests": 17}),
    ("Guests: 50.", {"guests": 50}),
    ("(7) gallons of decaf", {"gallons": [7]}),
])
def test_whole_matches_accepted(question, args):
    """Covers: AC-1 (right), EC-2, EC-14 (boundary). Whole words and whole digit runs are found."""
    assert check_arguments(args, question) is None


def test_no_item_in_question_not_constrained():
    """Covers: AC-1 (right), EC-8. A question naming no item does not constrain args['item']."""
    assert check_arguments({"item": "cups", "drinks": ["decaf"]}, "Tell me about decaf") is None

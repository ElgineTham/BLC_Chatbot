"""Spec 015 AC-6: check_arguments(..., tool="scale_recipe") (EC-19, EC-20). Unit; no I/O."""

from __future__ import annotations

import pytest

from blc.tool_step import REJECTED_PREFIX, check_arguments

SCALE = "scale_recipe"
Q90 = "How do I make lemonade for 90 guests?"


def test_row1_guests_in_question():
    """Covers: AC-6 (right), EC-19. Row 1: guests 90 appears."""
    assert check_arguments({"recipe": "lemonade", "guests": 90}, Q90, tool=SCALE) is None


def test_row2_invented_gallons_refused():
    """Covers: AC-6 (wrong), EC-19. Row 2: gallons 4 is not in the question."""
    r = check_arguments({"recipe": "lemonade", "gallons": 4}, Q90, tool=SCALE)
    assert isinstance(r, str) and r.startswith(REJECTED_PREFIX)
    assert "gallons" in r.lower()


def test_row3_spelled_number_counts():
    """Covers: AC-6 (right), EC-19. Row 3: 'six' as a word, gallons given as a list of one string."""
    args = {"recipe": "lemonade", "gallons": ["6"]}
    assert check_arguments(args, "Concentrate for six gallons of lemonade?", tool=SCALE) is None


def test_row4_everything_rule_does_not_apply():
    """Covers: AC-6 (right), EC-19. Row 4: scale_recipe ignores the 'item must be everything' rule,
    while the beverage tool (tool omitted) gives the 'everything' reason for the same args."""
    q = "What concentrate do I pack for lemonade for 70 guests?"
    args = {"recipe": "lemonade", "guests": 70}
    assert check_arguments(args, q, tool=SCALE) is None
    omitted = check_arguments(args, q)
    assert isinstance(omitted, str) and omitted.startswith(REJECTED_PREFIX)
    assert "everything" in omitted.lower()


def test_row5_number_one_always_accepted():
    """Covers: AC-6 (boundary), EC-19. Row 5: gallons 1 is accepted though the question has no 1 (spec 009)."""
    args = {"recipe": "lemonade", "gallons": 1}
    assert check_arguments(args, "How much concentrate for lemonade for 40 guests?", tool=SCALE) is None


def test_guests_list_ok():
    """Covers: AC-6 (right), EC-19. guests as a list of one value that is in the question."""
    assert check_arguments({"recipe": "lemonade", "guests": [90]}, "lemonade for 90 guests", tool=SCALE) is None


def test_guests_not_in_question_refused():
    """Covers: AC-6 (wrong), EC-19. Invented guest count."""
    r = check_arguments({"recipe": "lemonade", "guests": 50}, "How much lemonade?", tool=SCALE)
    assert isinstance(r, str) and r.startswith(REJECTED_PREFIX) and "guests" in r.lower()


def test_guests_numeric_string_checked():
    """Covers: AC-6 (wrong), EC-19. A numeric string is checked like a number."""
    assert check_arguments({"recipe": "lemonade", "guests": "90"}, Q90, tool=SCALE) is None
    r = check_arguments({"recipe": "lemonade", "guests": "40"}, Q90, tool=SCALE)
    assert isinstance(r, str) and r.startswith(REJECTED_PREFIX)


def test_number_only_inside_another_number_refused():
    """Covers: AC-6 (boundary), EC-19. 5 gallons is not in 'a 125 guest event' (spec 009 number rule)."""
    r = check_arguments({"recipe": "lemonade", "gallons": 5}, "Lemonade for a 125 guest event?", tool=SCALE)
    assert isinstance(r, str) and r.startswith(REJECTED_PREFIX)


@pytest.mark.parametrize("question", ["", "How do I make lemonade?", Q90])
def test_no_numbers_ok_for_any_question(question):
    """Covers: AC-6 (boundary), EC-19. A recipe name only has nothing to check."""
    assert check_arguments({"recipe": "lemonade"}, question, tool=SCALE) is None


@pytest.mark.parametrize("args", [{"gallons": object()}, {"recipe": "lemonade", "guests": object()},
                                  {}, {"recipe": None, "gallons": [None]}, {"guests": {"a": 1}}])
def test_odd_args_never_raise(args):
    """Covers: AC-6 (wrong), EC-19. Odd args never raise (the result is None or a refusal)."""
    r = check_arguments(args, Q90, tool=SCALE)
    assert r is None or r.startswith(REJECTED_PREFIX)


# ---- EC-20: spec 009 cases are unchanged with tool omitted or "calculate_bev_item" -----------------

BEV_CASES = [
    ({"item": "cups", "drinks": ["coffee"], "guests": 50}, "How many cups do I need for the mocha?", True),
    ({"item": "cups", "drinks": ["coffee"]}, "How many cups do I need for the mocha?", False),
    ({"item": "supplies", "drinks": ["decaf"], "guests": 85}, "What do I need to bring for decaf for 85 guests?", True),
    ({"item": "everything", "drinks": ["decaf"], "guests": 85}, "What do I need to bring for decaf for 85 guests?", False),
    ({"item": "cambros", "drinks": ["decaf"], "gallons": [12]}, "Which cambros for 12 gallons of decaf?", False),
    ({"item": "cambros", "drinks": ["decaf"], "gallons": [10, 2]}, "Which cambros for 12 gallons of decaf?", True),
    ({"item": "cambros", "drinks": ["decaf"], "gallons": [3], "guests": 70}, "Decaf for 70 guests, which cambros?", True),
    ({"item": "cambros", "drinks": ["decaf"], "gallons": [7]}, "Seven gallons of decaf, which containers?", False),
]


@pytest.mark.parametrize("args,question,refused", BEV_CASES)
def test_bev_cases_same_with_and_without_tool_argument(args, question, refused):
    """Covers: AC-6 (right/wrong), EC-20. Spec 009 results are identical with tool omitted and explicit."""
    omitted = check_arguments(args, question)
    explicit = check_arguments(args, question, tool="calculate_bev_item")
    assert omitted == explicit
    if refused:
        assert isinstance(omitted, str) and omitted.startswith(REJECTED_PREFIX)
    else:
        assert omitted is None

"""Spec 015 AC-4: raw arguments for run_recipe_tool (EC-14 to EC-16). Unit; never raises."""

from __future__ import annotations

import pytest

from blc.tools.recipe_tools import run_recipe_tool

GALLON_ARGS = [
    {"recipe": "lemonade", "gallons": 6},
    {"recipe": "lemonade", "gallons": "6"},
    {"recipe": "lemonade", "gallons": [6]},
    {"recipe": "lemonade", "gallons": ["6"]},
    {"recipe": "lemonade", "gallons": 6.0},
    {"recipe": ["lemonade"], "gallons": 6},
    {"drinks": ["lemonade"], "gallons": 6},
    {"drink": "lemonade", "gallons": 6},
    {"name": "lemonade", "gallons": 6},
    {"recipe": None, "name": "lemonade", "gallons": 6},
    {"recipe": "  ", "drink": "lemonade", "gallons": 6},
    {"recipe": "lemonade", "gallons": 6, "item": "cambros"},
]


@pytest.mark.parametrize("args", GALLON_ARGS, ids=[str(i) for i in range(len(GALLON_ARGS))])
def test_gallon_argument_shapes(book, ing, lemonade_steps, args):
    """Covers: AC-4 (right), EC-14. Each lenient shape gives the same result as 6 gallons of lemonade."""
    r = run_recipe_tool(args, book)
    assert r.status == "ok"
    assert r.recipe == "Lemonade"
    assert r.gallons == 6 and r.from_guests is False
    assert ing(r) == [("Lemon concentrate", 42, "oz", False), ("Water", 6, "gallon", True)]
    assert list(r.steps) == lemonade_steps


def test_decimal_string_gallons(book):
    """Covers: AC-4 (right), EC-14. A numeric string '2.5' is 5/2."""
    from fractions import Fraction
    r = run_recipe_tool({"recipe": "lemonade", "gallons": "2.5"}, book)
    assert r.status == "ok" and r.gallons == Fraction(5, 2)


def test_recipe_key_wins_over_alternates(book):
    """Covers: AC-4 (right), EC-14 (extra). A valid 'recipe' is used before 'drink'/'name'."""
    r = run_recipe_tool({"recipe": "lemonade", "name": "punch", "gallons": 2}, book)
    assert r.recipe == "Lemonade"


GUEST_ARGS = [
    {"recipe": "lemonade", "guests": 70},
    {"recipe": "lemonade", "guests": "70"},
    {"recipe": "lemonade", "guests": 70.0},
    {"recipe": "lemonade", "gallons": None, "guests": 70},
    {"recipe": "lemonade", "gallons": 0, "guests": 70},
    {"recipe": "lemonade", "gallons": [], "guests": 70},
]


@pytest.mark.parametrize("args", GUEST_ARGS, ids=[str(i) for i in range(len(GUEST_ARGS))])
def test_guest_argument_shapes(book, args):
    """Covers: AC-4 (right), EC-15. 70 guests is 3 gallons, 21 oz, from guests."""
    r = run_recipe_tool(args, book)
    assert r.status == "ok"
    assert r.gallons == 3 and r.ingredients[0].amount == 21
    assert r.from_guests is True


@pytest.mark.parametrize("args", [
    {"recipe": "lemonade"},
    {"recipe": "lemonade", "guests": 0},
    {"recipe": "lemonade", "guests": None},
    {"recipe": "lemonade", "gallons": 0, "guests": 0},
    {"recipe": "lemonade", "gallons": [], "guests": None},
])
def test_not_given_means_need_info(book, args):
    """Covers: AC-4 (boundary), EC-15. Missing, null and 0 amounts mean not given."""
    assert run_recipe_tool(args, book).status == "need_info"


@pytest.mark.parametrize("args", [
    {},
    {"recipe": None},
    {"recipe": 5},
    {"recipe": ""},
    {"recipe": ["lemonade", "fruit punch"], "gallons": 2},
    {"recipe": "lemonade", "gallons": -2},
    {"recipe": "lemonade", "gallons": "six"},
    {"recipe": "lemonade", "gallons": "6 gal"},
    {"recipe": "lemonade", "gallons": [6, 2]},
    {"recipe": "lemonade", "guests": -5},
    {"recipe": "lemonade", "guests": 2.5},
    {"recipe": "lemonade", "guests": "ninety"},
    {"recipe": "lemonade", "gallons": "-1"},
])
def test_invalid_arguments(book, args):
    """Covers: AC-4 (wrong), EC-16. Bad arguments give status invalid and do not raise."""
    r = run_recipe_tool(args, book)
    assert r.status == "invalid"
    assert r.text.lower().startswith("invalid")
    assert r.ingredients == () and r.steps == () and r.gallons is None


@pytest.mark.parametrize("args", [["lemonade"], "lemonade", None, 5, ("lemonade",)])
def test_non_mapping_invalid(book, args):
    """Covers: AC-4 (wrong), EC-16. args that is not a mapping is invalid."""
    assert run_recipe_tool(args, book).status == "invalid"


def test_precedence_invalid_over_no_recipe(book):
    """Covers: AC-4 (wrong), EC-10. Unknown drink with bad gallons is invalid."""
    assert run_recipe_tool({"recipe": "iced tea", "gallons": -2}, book).status == "invalid"


def test_no_recipe_for_unknown_name(book):
    """Covers: AC-4 (wrong), EC-8. An unknown drink in raw args gives no_recipe."""
    r = run_recipe_tool({"recipe": "iced tea", "gallons": 2}, book)
    assert r.status == "no_recipe" and r.recipe is None


def test_no_recipe_beats_need_info_raw(book):
    """Covers: AC-4 (boundary), EC-9. Unknown drink and no amounts is no_recipe."""
    assert run_recipe_tool({"recipe": "iced tea"}, book).status == "no_recipe"


def test_gallons_wins_over_guests_raw(book):
    """Covers: AC-4 (right), EC-6. gallons 4 and guests 120 in raw args."""
    r = run_recipe_tool({"recipe": "lemonade", "gallons": 4, "guests": 120}, book)
    assert r.gallons == 4 and r.from_guests is False


def test_odd_values_never_raise(book):
    """Covers: AC-4 (wrong), EC-16 (extra). Odd value types never raise; the ones section 4.5 covers
    ('anything else') are invalid."""
    for args in ({"recipe": "lemonade", "guests": {"a": 1}}, {"recipe": {"x": 1}, "gallons": 2}):
        assert run_recipe_tool(args, book).status == "invalid"
    # shapes the spec does not define: only "never raises"
    for args in ({"recipe": "lemonade", "gallons": object()}, {"recipe": "lemonade", "gallons": [[6]]},
                 {"recipe": {"x": 1}}):
        assert run_recipe_tool(args, book).status in ("invalid", "need_info", "ok")

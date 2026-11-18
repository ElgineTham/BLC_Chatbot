"""Spec 015 AC-3: the tool's text (EC-11 to EC-13). Only the parts listed in section 4.6 are checked."""

from __future__ import annotations

import re
from fractions import Fraction

import pytest

from blc.tools.recipe_tools import scale_recipe


def test_ok_text_parts(book, lemonade_steps):
    """Covers: AC-3 (right), EC-11. Name, ingredient lines, fill line, numbered steps in order."""
    t = scale_recipe("lemonade", gallons=6, book=book).text
    assert "Lemonade" in t
    assert "Lemon concentrate: 42 oz" in t
    assert "Water: fill to 6 gallons" in t
    for step in lemonade_steps:
        assert step in t
    positions = [t.index(s) for s in lemonade_steps]
    assert positions == sorted(positions)
    for n, step in enumerate(lemonade_steps, start=1):
        assert f"{n}." in t[: t.index(step)] and t[: t.index(step)].rstrip().endswith(f"{n}.")


def test_ok_text_numbering_starts_at_one(book):
    """Covers: AC-3 (boundary), EC-11. 'Fruit punch' has two steps, numbered 1. and 2., no 3."""
    t = scale_recipe("punch", gallons=2, book=book).text
    assert "1." in t and "2." in t
    assert "3." not in t.split("Water:")[-1]


def test_guest_text(book):
    """Covers: AC-3 (right), EC-11. 120 guests: 35 oz, 5 gallons, 'from 120 guests'."""
    t = scale_recipe("lemonade", guests=120, book=book).text
    assert "35 oz" in t and "5 gallons" in t and "from 120 guests" in t


def test_gallons_text_has_no_from_guests(book):
    """Covers: AC-3 (wrong), EC-11. A batch given in gallons is not labelled 'from N guests'."""
    t = scale_recipe("lemonade", gallons=4, guests=120, book=book).text
    assert "from 120 guests" not in t
    assert "4 gallons" in t


def test_decimal_formats(book):
    """Covers: AC-3 (boundary), EC-12. 2.5 gallons: 17.5 oz and '2.5 gallons'."""
    t = scale_recipe("lemonade", gallons=2.5, book=book).text
    assert "17.5 oz" in t and "2.5 gallons" in t


def test_two_decimals_max(book):
    """Covers: AC-3 (boundary), EC-12. 1/3 gallon: 7/3 oz shown as 2.33."""
    assert "2.33 oz" in scale_recipe("lemonade", gallons=Fraction(1, 3), book=book).text


def test_quarter_format(book):
    """Covers: AC-3 (boundary), EC-12 (extra). 0.75 style: punch 0.5 gallons gives 2.5 oz and 0.75 oz."""
    t = scale_recipe("punch", gallons=Fraction(1, 2), book=book).text
    assert "2.5 oz" in t and "0.75 oz" in t


def test_whole_numbers_have_no_decimals(book):
    """Covers: AC-3 (right), EC-12. 42, never 42.0."""
    t = scale_recipe("lemonade", gallons=6.0, book=book).text
    assert "42 oz" in t and "42.0" not in t and "6.0" not in t


def test_singular_gallon(book):
    """Covers: AC-3 (boundary), EC-12. Exactly 1 gallon is singular, never '1 gallons'."""
    t = scale_recipe("lemonade", gallons=1, book=book).text
    assert "1 gallon" in t
    assert not re.search(r"\b1 gallons\b", t)


def test_singular_gallon_from_guests(book):
    """Covers: AC-3 (boundary), EC-12. 10 guests is 1 gallon; singular, with 'from 10 guests'."""
    t = scale_recipe("lemonade", guests=10, book=book).text
    assert "1 gallon" in t and not re.search(r"\b1 gallons\b", t) and "from 10 guests" in t


def test_need_info_text(book):
    """Covers: AC-3 (right), EC-13. One question ending in '?' with 'gallons' and 'guests'."""
    t = scale_recipe("lemonade", book=book).text.strip()
    assert t.endswith("?")
    assert "gallons" in t and "guests" in t
    assert t.count("?") == 1


def test_no_recipe_text(book):
    """Covers: AC-3 (right), EC-13. Names the stripped request, 'no recipe', and every recipe."""
    t = scale_recipe(" Iced tea ", gallons=2, book=book).text
    assert "Iced tea" in t and "no recipe" in t.lower()
    assert "Lemonade" in t and "Fruit punch" in t


INVALID_CALLS = [
    {"recipe": "", "gallons": 2},
    {"recipe": "   ", "gallons": 2},
    {"recipe": "lemonade", "gallons": 0},
    {"recipe": "lemonade", "gallons": -2},
    {"recipe": "lemonade", "guests": 0},
    {"recipe": "lemonade", "guests": -5},
    {"recipe": "lemonade", "guests": 2.5},
]


@pytest.mark.parametrize("kwargs", INVALID_CALLS)
def test_invalid_text(book, kwargs):
    """Covers: AC-3 (wrong), EC-13, EC-10. Invalid text starts with 'invalid' and shows the format."""
    t = scale_recipe(book=book, **kwargs).text
    assert t.lower().startswith("invalid")
    assert '"recipe"' in t and '"gallons"' in t and '"guests"' in t


def test_invalid_text_for_raw_args(book):
    """Covers: AC-3 (wrong), EC-13, EC-16. Invalid text from run_recipe_tool has the same shape."""
    from blc.tools.recipe_tools import run_recipe_tool
    for args in ({}, {"recipe": "lemonade", "gallons": "six"}, ["lemonade"]):
        t = run_recipe_tool(args, book).text
        assert t.lower().startswith("invalid")
        assert '"recipe"' in t and '"gallons"' in t and '"guests"' in t

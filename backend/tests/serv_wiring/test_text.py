"""Spec 043 section 6.6 TEXT-1 to TEXT-5 (AC-9): the 'Counted for:' reading in the tool's text. Unit, with the
spec 042 Appendix A rules (conftest `rules`)."""
from __future__ import annotations

import pytest

from blc.tools.serv_tools import run_serv_tool

LABEL = "Counted for:"


def _run(rules, items):
    return run_serv_tool({"items": items}, rules=rules)


def _reading(text):
    """The reading: everything after the label, casefolded."""
    assert LABEL in text, text
    return text.split(LABEL, 1)[1].casefold()


# ---------------------------------------------------------------- TEXT-1

def test_text_1_reading_shows_food_and_quantity_and_unit(rules):
    """Covers: AC-9 (right), TEXT-1. Croissants 70 each: the text has 'Counted for:', and after it 'butter
    croissants' and '70 each'."""
    r = _run(rules, [{"food": "butter croissants", "qty": 70, "unit": "each"}])
    assert r.status == "ok"
    reading = _reading(r.text)
    assert "butter croissants" in reading
    assert "70 each" in reading


def test_reading_is_the_last_line_and_label_is_exact(rules):
    """Covers: AC-9 (boundary), TEXT-1. The text ends with a line that starts with 'Counted for:' (exact
    capitalisation), and the label appears once."""
    r = _run(rules, [{"food": "butter croissants", "qty": 70, "unit": "each"}])
    last = r.text.rstrip().splitlines()[-1]
    assert last.startswith(LABEL)
    assert r.text.count(LABEL) == 1


def test_spec_042_text_is_still_there(rules):
    """Covers: AC-9 (right), TEXT-1. The utensil lines of spec 042 stay, before the reading."""
    r = _run(rules, [{"food": "butter croissants", "qty": 3}])
    assert "Small tongs: 4" in r.text
    assert r.text.index("Small tongs: 4") < r.text.index(LABEL)


def test_empty_ok_text_has_the_reading_too(rules):
    """Covers: AC-9 (boundary), TEXT-4. A result with no utensils keeps its sentence and also ends with the
    reading (trail mix 12 bags)."""
    r = _run(rules, [{"food": "trail mix", "qty": 12}])
    assert r.status == "ok" and r.utensils == {}
    assert "no serving utensils" in r.text.lower()
    assert r.text.rstrip().splitlines()[-1].startswith(LABEL)
    assert "trail mix 12 bags" in _reading(r.text)


# ---------------------------------------------------------------- TEXT-2

def test_text_2_no_unit_shows_the_foods_own_unit(rules):
    """Covers: AC-9 (right), TEXT-2. Croissants 3 with no unit: the reading says '3 dozen'."""
    r = _run(rules, [{"food": "butter croissants", "qty": 3}])
    assert "butter croissants 3 dozen" in _reading(r.text)


def test_each_food_own_unit_is_each(rules):
    """Covers: AC-9 (right), TEXT-2. Deli sandwiches 50 with no unit: '50 each'."""
    r = _run(rules, [{"food": "classic deli sandwiches", "qty": 50}])
    assert "classic deli sandwiches 50 each" in _reading(r.text)


def test_given_unit_is_the_unit_used(rules):
    """Covers: AC-9 (right), TEXT-2. Deli sandwiches 2 with unit 'dozen': the unit shown is the unit used,
    'dozen' (not the food's own 'each')."""
    r = _run(rules, [{"food": "classic deli sandwiches", "qty": 2, "unit": "dozen"}])
    reading = _reading(r.text)
    assert "2 dozen" in reading
    assert "2 each" not in reading


def test_unit_spelling_is_shown_canonically(rules):
    """Covers: AC-9 (boundary), TEXT-2. Unit given as 'dz': the reading shows 'dozen'."""
    r = _run(rules, [{"food": "butter croissants", "qty": 3, "unit": "dz"}])
    assert r.status == "ok"
    assert "3 dozen" in _reading(r.text)


def test_alias_is_shown_as_the_canonical_food(rules):
    """Covers: AC-9 (right), TEXT-2. Food given by an alias ('bagels'): the reading names the canonical food."""
    r = _run(rules, [{"food": "bagels", "qty": 2}])
    assert "assorted bagels 2 dozen" in _reading(r.text)


# ---------------------------------------------------------------- TEXT-3

@pytest.mark.parametrize("qty, unit, shown, not_shown", [
    (2.5, "dozen", "2.5 dozen", "2.50"),
    (70.0, "each", "70 each", "70.0"),
    (3.0, None, "3 dozen", "3.0"),
    (1.25, "dozen", "1.25 dozen", None),
    ("3", None, "3 dozen", None),
])
def test_text_3_number_formatting(rules, qty, unit, shown, not_shown):
    """Covers: AC-9 (boundary), TEXT-3. Whole numbers show without a decimal, other numbers with up to 2
    decimals."""
    item = {"food": "butter croissants", "qty": qty}
    if unit:
        item["unit"] = unit
    r = _run(rules, [item])
    assert r.status == "ok", r.text
    reading = _reading(r.text)
    assert shown in reading
    if not_shown:
        assert not_shown not in r.text


# ---------------------------------------------------------------- TEXT-4

def test_text_4_lines_are_in_input_order(rules):
    """Covers: AC-9 (right), TEXT-4. Trail mix 12 + croissants 1 dozen: both appear in the reading, trail mix
    first (input order), each with its own unit."""
    r = _run(rules, [{"food": "trail mix", "qty": 12}, {"food": "butter croissants", "qty": 1, "unit": "dozen"}])
    reading = _reading(r.text)
    assert "trail mix 12 bags" in reading
    assert "butter croissants 1 dozen" in reading
    assert reading.index("trail mix") < reading.index("butter croissants")


def test_reversed_input_gives_reversed_reading(rules):
    """Covers: AC-9 (boundary), TEXT-4. The same two lines in the other order flip in the reading, so the
    order follows the input and not the food names."""
    r = _run(rules, [{"food": "butter croissants", "qty": 1, "unit": "dozen"}, {"food": "trail mix", "qty": 12}])
    reading = _reading(r.text)
    assert reading.index("butter croissants") < reading.index("trail mix")


def test_same_food_twice_is_read_twice(rules):
    """Covers: AC-9 (boundary), TEXT-4. One reading per input line: croissants listed twice appear twice."""
    r = _run(rules, [{"food": "butter croissants", "qty": 1}, {"food": "butter croissants", "qty": 2}])
    reading = _reading(r.text)
    assert reading.count("butter croissants") == 2
    assert reading.index("1 dozen") < reading.index("2 dozen")


def test_three_lines_all_read(rules):
    """Covers: AC-9 (right), TEXT-4. The 70-guest Cascade shape: several item lines plus a package-style line
    each get a reading, in input order."""
    r = _run(rules, [{"food": "butter croissants", "qty": 70, "unit": "each"},
                     {"food": "tabbouleh salad", "qty": 70, "unit": "each"},
                     {"food": "classic deli sandwiches", "qty": 70, "unit": "each"}])
    reading = _reading(r.text)
    order = [reading.index(x) for x in ("butter croissants 70 each", "quinoa-chickpea tabbouleh salad 70 each",
                                        "classic deli sandwiches 70 each")]
    assert order == sorted(order)


# ---------------------------------------------------------------- TEXT-5

def test_text_5_need_info_has_no_reading(rules):
    """Covers: AC-9 (wrong), TEXT-5. Croissants with no qty (need_info): no 'Counted for:' in the text."""
    r = _run(rules, [{"food": "butter croissants"}])
    assert r.status == "need_info"
    assert LABEL not in r.text


def test_text_5_invalid_has_no_reading(rules):
    """Covers: AC-9 (wrong), TEXT-5. Food 'lasagna' (invalid): no 'Counted for:' in the text."""
    r = _run(rules, [{"food": "lasagna", "qty": 3}])
    assert r.status == "invalid"
    assert LABEL not in r.text


def test_other_invalid_shapes_have_no_reading(rules):
    """Covers: AC-9 (wrong), TEXT-5. Invalid for other reasons (negative qty, unit mismatch, empty items):
    still no reading."""
    for items in ([{"food": "butter croissants", "qty": -2}],
                  [{"food": "butter croissants", "qty": 3, "unit": "bags"}],
                  []):
        r = _run(rules, items)
        assert r.status == "invalid"
        assert LABEL not in r.text

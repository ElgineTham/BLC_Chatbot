"""format_pull_sheet (spec 002 §4.6, EC-28, AC-11). Moved from tests/test_pull_sheet.py."""
from fractions import Fraction

import pytest

from pull_sheet import (
    NOT_ON_MENU,
    UNKNOWN_UNIT,
    BeoLine,
    PullLine,
    PullSheet,
    Skipped,
    format_pull_sheet,
)


def _l(supply, q):
    return PullLine(supply, q, ())


def test_format_spec_example():
    """Covers: AC-11 (right). Exactly the §4.6 example text."""
    sheet = PullSheet(
        70,
        (
            _l("5 gal cambro", 5), _l("Oatmilk", 1), _l("hot-cups", 120), _l("cold-cups", 120),
            _l("Cocktail napkins", None), _l("Creamer", None), _l("Stir sticks", 1), _l("Sugar", 1),
        ),
        (Skipped(BeoLine("Cascade Breakfast", Fraction(70), "Packages"), NOT_ON_MENU),),
    )
    assert format_pull_sheet(sheet) == (
        "Pull sheet for 70 guests\n"
        "\n"
        "Beverages\n"
        "- 5 gal cambro: 5\n"
        "- Oatmilk: 1\n"
        "- hot-cups: 120\n"
        "- cold-cups: 120\n"
        "- Cocktail napkins: ✓\n"
        "- Creamer: ✓\n"
        "- Stir sticks: 1\n"
        "- Sugar: 1\n"
        "\n"
        "Not used (check by hand):\n"
        "- Cascade Breakfast, 70 Packages: not on beverage menu\n"
    )


def test_format_none_and_no_skipped_block():
    """Covers: AC-11 (boundary), EC-28. No lines -> '- (none)'; no skipped -> no 'Not used' block."""
    assert format_pull_sheet(PullSheet(5, (), ())) == (
        "Pull sheet for 5 guests\n\nBeverages\n- (none)\n"
    )


def test_format_none_with_skipped():
    """Covers: AC-11 (right), EC-28. '- (none)' and the skipped block together."""
    s = Skipped(BeoLine("Cascade Breakfast", Fraction(70), "Packages"), NOT_ON_MENU)
    assert format_pull_sheet(PullSheet(70, (), (s,))) == (
        "Pull sheet for 70 guests\n\nBeverages\n- (none)\n\n"
        "Not used (check by hand):\n- Cascade Breakfast, 70 Packages: not on beverage menu\n"
    )


def test_format_blank_unit_skipped():
    """Covers: AC-11 (boundary). Blank unit -> '- <name>, <qty>: <problem>' with no trailing space or extra comma."""
    s = Skipped(BeoLine("Oatmilk", Fraction(1), ""), UNKNOWN_UNIT)
    out = format_pull_sheet(PullSheet(10, (_l("Sugar", 1),), (s,)))
    assert out.endswith("Not used (check by hand):\n- Oatmilk, 1: unknown unit\n")


@pytest.mark.parametrize(
    "qty,text",
    [
        (Fraction(70), "70"),
        (Fraction(3, 2), "1.5"),
        (Fraction(1, 2), "0.5"),
        (Fraction(7, 4), "1.75"),
        (Fraction(1, 8), "0.125"),
        (Fraction(1, 3), "1/3"),
        (Fraction(2, 3), "2/3"),
        (Fraction(10, 1), "10"),
    ],
)
def test_format_skipped_qty_rendering(qty, text):
    """Covers: AC-11 (boundary). Skipped qty: integer if whole, shortest exact decimal if one exists, else a/b."""
    s = Skipped(BeoLine("Mystery", qty, "Trays"), NOT_ON_MENU)
    out = format_pull_sheet(PullSheet(10, (), (s,)))
    assert f"- Mystery, {text} Trays: not on beverage menu\n" in out


def test_format_multiple_skipped_in_order_and_single_trailing_newline():
    """Covers: AC-11 (right). Skipped lines in given order; text ends with exactly one newline."""
    s1 = Skipped(BeoLine("B item", Fraction(1), "Each"), NOT_ON_MENU)
    s2 = Skipped(BeoLine("A item", Fraction(2), "Gallon"), UNKNOWN_UNIT)
    out = format_pull_sheet(PullSheet(10, (_l("Sugar", 1),), (s1, s2)))
    assert out.endswith("- B item, 1 Each: not on beverage menu\n- A item, 2 Gallon: unknown unit\n")
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_format_singular_guest_count():
    """Covers: AC-11 (boundary). One guest still reads 'guests' (format is fixed)."""
    out = format_pull_sheet(PullSheet(1, (), ()))
    assert out.splitlines()[0] == "Pull sheet for 1 guests"


def test_format_does_not_show_reasons():
    """Covers: AC-11 (wrong), §2. Reasons are not shown in the CLI text."""
    sheet = PullSheet(10, (PullLine("Sugar", 1, ("rules/beverages.json supplies[5]",)),), ())
    assert "supplies[5]" not in format_pull_sheet(sheet)

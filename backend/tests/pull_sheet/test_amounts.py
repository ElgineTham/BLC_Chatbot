"""Packages, placeholders, guests to gallons, own vs package, skipped lines
(spec 002 §4.5 steps 1-2, EC-1 to EC-13). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
from fractions import Fraction

import pytest

from pull_sheet import NOT_ON_MENU, UNKNOWN_UNIT, Beo, BeoLine, Skipped, build_pull_sheet

PKG = "Coffee, decaf, tea, iced water & juice"
PKG3 = (PKG, 3, "Gallons")


# --------------------------------------------------------------------------
# AC-3: packages and guest -> gallon conversion
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "guests,expected",
    [
        (1, 1), (10, 1), (12, 1), (13, 1), (25, 1), (37, 1), (38, 2),
        (60, 2), (62, 2), (63, 3), (70, 3), (75, 3), (87, 3), (88, 4),
    ],
)
def test_guest_to_gallons_rounding(tmp_path, guests, expected, run, gal):
    """Covers: AC-3 (boundary), EC-3, EC-11, NFR-2. Blank-unit item qty is guests; 25/gal, half-up, min 1."""
    sheet = run(tmp_path, guests, [("Fresh-brewed coffee", guests, "")])
    assert gal(sheet, "Coffee") == expected


@pytest.mark.parametrize("qty,expected", [("12.5", 1), ("37.5", 2), ("62.5", 3), ("62.4", 2)])
def test_guest_to_gallons_half_exactly(tmp_path, qty, expected, run, gal):
    """Covers: AC-3 (boundary), EC-3, NFR-2. Exactly .5 rounds up (62.5/25 = 2.5 -> 3); below rounds down."""
    sheet = run(tmp_path, 70, [("Coffee", qty, "")])
    assert gal(sheet, "Coffee") == expected


def test_package_blank_unit_expands_to_five_items(tmp_path, run, gal, qtys, line_of):
    """Covers: AC-3 (right), EC-1. Package 70 guests -> five items with 3 gal each, one 5 gal cambro each."""
    sheet = run(tmp_path, 70, [(PKG, 70, "")])
    for item in ["Coffee", "Decaf", "Hot water", "Iced water", "Orange juice"]:
        assert gal(sheet, item) == 3
    assert gal(sheet, "Pomegranate juice") == 0
    assert qtys(sheet)["5 gal cambro"] == 5
    assert "2 gal cambro" not in qtys(sheet)
    assert "1 gal cambro" not in qtys(sheet)
    reasons = line_of(sheet, "5 gal cambro").reasons
    assert len(reasons) == 5
    for item in ["Coffee", "Decaf", "Hot water", "Iced water", "Orange juice"]:
        assert sum(item in r for r in reasons) == 1


def test_package_one_gallon(tmp_path, run, gal, qtys):
    """Covers: AC-3 (right), EC-2. Package with '1 Gallon' -> 1 gal of each of the five."""
    sheet = run(tmp_path, 70, [(PKG, 1, "Gallon")])
    for item in ["Coffee", "Decaf", "Hot water", "Iced water", "Orange juice"]:
        assert gal(sheet, item) == 1
    assert qtys(sheet)["1 gal cambro"] == 5


def test_package_gallons_unit_variants(tmp_path, run, gal):
    """Covers: AC-3 (right). 'gallons' and 'GALLON' both mean gallons (normalized)."""
    s1 = run(tmp_path, 70, [(PKG, 4, "Gallons")])
    s2 = run(tmp_path, 70, [(PKG, 4, "  GALLON ")])
    assert gal(s1, "Coffee") == 4
    assert gal(s2, "Coffee") == 4


def test_package_name_normalized(tmp_path, run, gal):
    """Covers: AC-3 (right), §4.2. Package line matches after casefold/whitespace collapse."""
    sheet = run(tmp_path, 70, [("  COFFEE,  DECAF, tea, iced water &   juice ", 70, "")])
    assert sheet.skipped == ()
    assert gal(sheet, "Coffee") == 3


def test_package_unit_packages_unknown(tmp_path, run):
    """Covers: AC-3 (wrong), AC-9, EC-10. Package line with unit 'Packages' -> UNKNOWN_UNIT, nothing ordered."""
    line = (PKG, 70, "Packages")
    sheet = run(tmp_path, 70, [line])
    assert sheet.skipped == (Skipped(BeoLine(PKG, Fraction(70), "Packages"), UNKNOWN_UNIT),)
    assert sheet.lines == ()


def test_package_each_unit_unknown(tmp_path, run):
    """Covers: AC-3 (wrong), AC-9. Package line with unit 'Each' -> UNKNOWN_UNIT."""
    sheet = run(tmp_path, 70, [(PKG, 70, "Each")])
    assert [s.problem for s in sheet.skipped] == [UNKNOWN_UNIT]


def test_package_small_guest_count_minimum_one_gallon(tmp_path, run, gal):
    """Covers: AC-3 (boundary), EC-3. Package for 5 guests -> minimum 1 gal each."""
    sheet = run(tmp_path, 5, [(PKG, 5, "")])
    assert gal(sheet, "Coffee") == 1


def test_two_package_lines_sum(tmp_path, run, gal):
    """Covers: AC-3 (right), AC-4. pkg is the sum over all package lines including the item."""
    sheet = run(tmp_path, 70, [(PKG, 3, "Gallons"), (PKG, 2, "Gallons")])
    assert gal(sheet, "Coffee") == 5
    assert gal(sheet, "Orange juice") == 5


def test_item_gallons_unit(tmp_path, run, gal):
    """Covers: AC-3 (right). Item with gallon unit uses qty gallons."""
    sheet = run(tmp_path, 70, [("Fresh-brewed coffee", 2, "Gallon")])
    assert gal(sheet, "Coffee") == 2


def test_item_blank_unit_is_guests(tmp_path, run, gal, qtys):
    """Covers: AC-3 (right), EC-11. Fresh-brewed coffee 70 with blank unit -> 3 gal."""
    sheet = run(tmp_path, 70, [("Fresh-brewed coffee", 70, "")])
    assert gal(sheet, "Coffee") == 3
    assert qtys(sheet)["5 gal cambro"] == 1


# --------------------------------------------------------------------------
# AC-4: placeholders and own/pkg
# --------------------------------------------------------------------------
def test_ec4_package_plus_same_juice_not_doubled(tmp_path, run, gal, qtys):
    """Covers: AC-4 (right), EC-4. Package 70 + Orange juice 70 -> OJ 3 gal, not 6."""
    sheet = run(tmp_path, 70, [(PKG, 70, ""), ("Orange juice", 70, "")])
    assert gal(sheet, "Orange juice") == 3
    assert qtys(sheet)["5 gal cambro"] == 5
    assert "1 gal cambro" not in qtys(sheet)


def test_ec5_package_small_own_large(tmp_path, run, gal):
    """Covers: AC-4 (right), EC-5. Package 1 gal + Coffee 3 gal -> Coffee 3 (larger), not 4."""
    sheet = run(tmp_path, 70, [(PKG, 1, "Gallon"), ("Fresh-brewed coffee", 3, "Gallon")])
    assert gal(sheet, "Coffee") == 3
    assert gal(sheet, "Decaf") == 1


def test_ec5_package_large_own_small(tmp_path, run, gal):
    """Covers: AC-4 (right), EC-5. Package 3 gal + Coffee 1 gal -> Coffee 3."""
    sheet = run(tmp_path, 70, [(PKG, 3, "Gallons"), ("Coffee", 1, "Gallon")])
    assert gal(sheet, "Coffee") == 3


def test_ec5_equal_amounts_not_doubled(tmp_path, run, gal):
    """Covers: AC-4 (boundary), EC-5. Equal own and pkg -> counted once."""
    sheet = run(tmp_path, 70, [(PKG, 3, "Gallons"), ("Coffee", 3, "Gallon")])
    assert gal(sheet, "Coffee") == 3


@pytest.mark.parametrize(
    "extra_lines,oj,pom",
    [
        ([("Orange juice", 3, "Gallons"), ("Pomegranate juice", 4, "Gallons")], 3, 4),
        ([("Pomegranate juice", 4, "Gallons")], 0, 4),
        ([("Pomegranate juice", 1, "Gallons")], 0, 1),
        ([], 3, 0),
    ],
    ids=["oj+pom", "pom-only-4", "pom-only-1", "no-juice"],
)
def test_ec5a_placeholders(tmp_path, extra_lines, oj, pom, run, gal):
    """Covers: AC-4 (right/boundary), EC-5a. Placeholder dropped when any juice has its own line."""
    sheet = run(tmp_path, 70, [PKG3] + extra_lines)
    assert gal(sheet, "Orange juice") == oj
    assert gal(sheet, "Pomegranate juice") == pom


def test_placeholder_line_order_irrelevant(tmp_path, run, gal):
    """Covers: AC-4 (right), EC-5a. Juice line listed before the package still drops the placeholder."""
    sheet = run(tmp_path, 70, [("Pomegranate juice", 4, "Gallons"), PKG3])
    assert gal(sheet, "Orange juice") == 0
    assert gal(sheet, "Pomegranate juice") == 4


@pytest.mark.parametrize(
    "bad_line,problem",
    [
        (("Mango juice", 2, "Gallons"), NOT_ON_MENU),
        (("Orange juice", 2, "Each"), UNKNOWN_UNIT),
        (("Pomegranate juice", 2, "Packages"), UNKNOWN_UNIT),
    ],
)
def test_ec5b_skipped_juice_does_not_drop_placeholder(tmp_path, bad_line, problem, run, gal):
    """Covers: AC-4 (wrong), EC-5b. A skipped juice line does not drop the placeholder."""
    sheet = run(tmp_path, 70, [PKG3, bad_line])
    assert gal(sheet, "Orange juice") == 3
    assert gal(sheet, "Pomegranate juice") == 0
    assert [s.problem for s in sheet.skipped] == [problem]


def test_ec5c_package_tea_is_hot_water_and_iced_tea_kept(tmp_path, run, gal):
    """Covers: AC-4 (right), EC-5c. Package + Iced tea 5 gal -> Hot water 3 (package) and Iced tea 5."""
    sheet = run(tmp_path, 70, [PKG3, ("Iced tea with lemon wedges", 5, "Gallons")])
    assert gal(sheet, "Hot water") == 3
    assert gal(sheet, "Iced tea") == 5


def test_ec6_own_lines_add_up(tmp_path, run, gal, qtys):
    """Covers: AC-4 (right), EC-6. Two own lines 2 + 3 gal -> 5 gal -> one 5 gal cambro."""
    sheet = run(
        tmp_path, 70, [("Fresh-brewed coffee", 2, "Gallon"), ("Fresh-brewed coffee", 3, "Gallon")]
    )
    assert gal(sheet, "Coffee") == 5
    assert qtys(sheet)["5 gal cambro"] == 1
    assert "1 gal cambro" not in qtys(sheet)


def test_own_lines_via_name_and_alias_add_up(tmp_path, run, gal):
    """Covers: AC-4 (right), EC-6. Item name and 'also written as' both count as own lines."""
    sheet = run(tmp_path, 70, [("Coffee", 2, "Gallon"), ("Fresh-brewed coffee", 3, "Gallon")])
    assert gal(sheet, "Coffee") == 5


def test_own_sum_vs_package_max_not_sum_of_all(tmp_path, run, gal):
    """Covers: AC-4 (boundary), EC-5/EC-6. own = 2+2 = 4, pkg = 3 -> max = 4."""
    sheet = run(
        tmp_path, 70, [PKG3, ("Coffee", 2, "Gallon"), ("Fresh-brewed coffee", 2, "Gallon")]
    )
    assert gal(sheet, "Coffee") == 4


# --------------------------------------------------------------------------
# AC-9: skipped lines
# --------------------------------------------------------------------------
def test_ec8_normalization_matches(tmp_path, run, gal):
    """Covers: AC-9 (right), EC-8, §4.2. Case and whitespace differences still match."""
    sheet = run(tmp_path, 70, [("  FRESH-BREWED   coffee ", 2, "Gallon")])
    assert sheet.skipped == ()
    assert gal(sheet, "Coffee") == 2


def test_ec8_punctuation_kept(tmp_path, make_catalog):
    """Covers: AC-9 (wrong), EC-8. 'Fresh brewed coffee' (no hyphen) -> NOT_ON_MENU."""
    line = BeoLine("Fresh brewed coffee", Fraction(2), "Gallon")
    cat = make_catalog(tmp_path, probe=True)
    sheet = build_pull_sheet(cat, Beo(70, (line,)))
    assert sheet.skipped == (Skipped(line, NOT_ON_MENU),)
    assert sheet.lines == ()


def test_ec7_alias_with_commas(tmp_path, run, gal):
    """Covers: AC-9 (right), EC-7. A name with commas matches its alias exactly."""
    sheet = run(
        tmp_path, 70,
        [("Hot water with an assortment of black, green, and herbal tea bags", 2, "Gallons")],
    )
    assert sheet.skipped == ()
    assert gal(sheet, "Hot water") == 2


def test_ec10_unknown_units(tmp_path, run):
    """Covers: AC-9 (wrong), EC-10. Wrong units for each item, gallon item and package -> UNKNOWN_UNIT."""
    lines = [
        ("Oatmilk", 1, "Gallon"),
        ("Fresh-brewed coffee", 2, "Each"),
        (PKG, 70, "Packages"),
        ("Fresh-brewed coffee", 2, "Quarts"),
    ]
    sheet = run(tmp_path, 70, lines)
    assert [s.problem for s in sheet.skipped] == [UNKNOWN_UNIT] * 4
    assert [s.line.name for s in sheet.skipped] == [l[0] for l in lines]
    assert sheet.lines == ()


def test_ec12_non_beverage_lines_trigger_nothing(tmp_path, run):
    """Covers: AC-9 (wrong), EC-12. Food lines and Cascade Breakfast -> NOT_ON_MENU and no rules fire."""
    lines = [("Cascade Breakfast", 70, "Packages"), ("Chicken Marsala", 3, "Trays"), ("Bottled water", 10, "")]
    sheet = run(tmp_path, 70, lines)
    assert [s.problem for s in sheet.skipped] == [NOT_ON_MENU] * 3
    assert sheet.lines == ()


def test_skipped_in_beo_order_and_alongside_used(tmp_path, run, gal, names):
    """Covers: AC-9 (right), EC-12. Skipped keep BEO order; used lines are unaffected."""
    lines = [
        ("Zeta food", 1, "Each"),
        ("Coffee", 2, "Gallon"),
        ("Oatmilk", 1, "Gallon"),
        ("Alpha food", 1, ""),
    ]
    sheet = run(tmp_path, 70, lines)
    assert [(s.line.name, s.problem) for s in sheet.skipped] == [
        ("Zeta food", NOT_ON_MENU),
        ("Oatmilk", UNKNOWN_UNIT),
        ("Alpha food", NOT_ON_MENU),
    ]
    assert gal(sheet, "Coffee") == 2
    assert "Oatmilk" not in names(sheet)


def test_skipped_holds_original_line(tmp_path, make_catalog):
    """Covers: AC-9 (right). Skipped.line is the BEO line as given (unnormalized)."""
    line = BeoLine("  Mystery   Dish ", Fraction(3, 2), " Trays ")
    sheet = build_pull_sheet(make_catalog(tmp_path), Beo(10, (line,)))
    assert sheet.skipped[0].line == line


def test_empty_beo_lines_gives_empty_sheet(tmp_path, run):
    """Covers: AC-9 (boundary), EC-28. A BEO with no lines -> no pull lines, no skipped."""
    sheet = run(tmp_path, 70, [])
    assert sheet.lines == ()
    assert sheet.skipped == ()
    assert sheet.guests == 70

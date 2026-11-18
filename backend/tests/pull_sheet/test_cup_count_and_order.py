"""Cup count base and item order (spec 002 AC-14, AC-15, EC-30, EC-31). Moved from tests/test_pull_sheet.py.

The CLI header check for EC-30 is in test_cli.py; the hash-seed check for EC-31 is in test_determinism.py.
Shared helpers come from conftest.py as fixtures.
"""
import pytest

PKG = "Coffee, decaf, tea, iced water & juice"
ITEM_ORDER = ["Coffee", "Decaf", "Hot water", "Iced water", "Orange juice"]


# --------------------------------------------------------------------------
# AC-14: cup count base G (Revision 1, EC-30)
# --------------------------------------------------------------------------
def test_ec30_guest_count_below_package_line(tmp_path, run, qtys):
    """Covers: AC-14 (right), EC-30. Guest Count 50 + package line 70 (blank unit) -> G = 70 -> 70 + 50 = 120;
    PullSheet.guests still shows the Guest Count."""
    sheet = run(tmp_path, 50, [(PKG, 70, "")], probe=False)
    assert qtys(sheet)["hot-cups"] == 120
    assert qtys(sheet)["cold-cups"] == 120
    assert sheet.guests == 50


@pytest.mark.parametrize(
    "guests,lines,expected",
    [
        (70, [(PKG, 50, "")], 120),                                   # Guest Count is larger -> G = 70
        (70, [(PKG, 70, "")], 120),                                   # equal
        (15, [(PKG, 30, "")], 50),                                    # tier chosen by G (30 -> +20), not by 15 (+10)
        (20, [(PKG, 21, "")], 41),                                    # G = 21 crosses the 20-guest tier boundary
        (15, [("Fresh-brewed coffee", 30, "")], 50),                  # item line with blank unit counts too
        (50, [("Fresh-brewed coffee", 90, "Gallon")], 70),            # gallon lines do not count toward G
        (50, [("Coffee", 1, "Gallon"), (PKG, 90, "Gallons")], 70),    # package in gallons does not count
        (15, [("Coffee", 1, "Gallon"), ("Mango juice", 200, "")], 25),  # skipped (not on menu) line does not raise G
        (50, [("Coffee", 1, "Gallon"), (PKG, 200, "Packages")], 70),  # skipped (unknown unit) line does not raise G
    ],
    ids=[
        "guests-larger", "equal", "tier-by-G", "tier-boundary-by-G", "item-blank-unit",
        "gallon-item-ignored", "gallon-package-ignored", "skipped-not-on-menu", "skipped-unknown-unit",
    ],
)
def test_ec30_cup_count_base(tmp_path, guests, lines, expected, run, qtys):
    """Covers: AC-14 (right/wrong/boundary), EC-30. G = max(Guest Count, qty of matched blank-unit lines);
    hot-cups = G + extra(G)."""
    sheet = run(tmp_path, guests, lines, probe=False)
    assert qtys(sheet)["hot-cups"] == expected
    assert sheet.guests == guests


@pytest.mark.parametrize("guests,pkg_qty", [(50, 70), (70, 50)])
def test_per_guest_uses_cup_count_base(tmp_path, guests, pkg_qty, rules_with, run, qtys):
    """Covers: AC-14 (right). `guest` entries use G too: 1 per guest -> 70."""
    rules = rules_with([{"supply": "Napkins", "qty": 1, "per": "guest", "when_tagged": "HOT"}])
    sheet = run(tmp_path, guests, [(PKG, pkg_qty, "")], rules=rules, probe=False)
    assert qtys(sheet)["Napkins"] == 70


def test_cup_count_base_fractional_line_qty_exact(tmp_path, rules_with, run, qtys):
    """Covers: AC-14 (boundary), NFR-2. A blank-unit qty of 62.5 gives G = 62.5; 1 per guest -> ceil = 63."""
    rules = rules_with([{"supply": "Napkins", "qty": 1, "per": "guest"}])
    sheet = run(tmp_path, 10, [("Coffee", "62.5", "")], rules=rules, probe=False)
    assert qtys(sheet)["Napkins"] == 63


# --------------------------------------------------------------------------
# AC-15: item order (Revision 1, EC-31)
# --------------------------------------------------------------------------
def _assert_reason_items_in_order(reasons, expected_items):
    assert len(reasons) == len(expected_items), reasons
    for reason, item in zip(reasons, expected_items):
        assert item in reason, (reason, item)


def test_ec31_package_item_order(tmp_path, run, line_of):
    """Covers: AC-15 (right), EC-31. Package at 70 -> 5 gal cambro reasons name Coffee, Decaf, Hot water,
    Iced water, Orange juice in that order."""
    sheet = run(tmp_path, 70, [(PKG, 70, "")], probe=False)
    _assert_reason_items_in_order(line_of(sheet, "5 gal cambro").reasons, ITEM_ORDER)


def test_item_order_follows_package_includes_order(tmp_path, default_menu, run, line_of):
    """Covers: AC-15 (right), §4.5-2. Items from one package line follow that package's `includes` order."""
    menu = default_menu()
    menu["packages"][PKG]["includes"] = ["Iced water", "Hot water", "Decaf", "Coffee"]
    sheet = run(tmp_path, 70, [(PKG, 70, "")], menu=menu, probe=False)
    _assert_reason_items_in_order(
        line_of(sheet, "5 gal cambro").reasons,
        ["Iced water", "Hot water", "Decaf", "Coffee", "Orange juice"],
    )


@pytest.mark.parametrize(
    "placeholders,expected_tail",
    [
        ({"JUICE": "Orange juice", "TEA": "Iced tea"}, ["Orange juice", "Iced tea"]),
        ({"TEA": "Iced tea", "JUICE": "Orange juice"}, ["Iced tea", "Orange juice"]),
    ],
    ids=["juice-then-tea", "tea-then-juice"],
)
def test_item_order_placeholders_in_written_order(
    tmp_path, placeholders, expected_tail, default_menu, run, line_of
):
    """Covers: AC-15 (right/boundary), §4.5-2. After `includes`, placeholder defaults follow in the order written."""
    menu = default_menu()
    menu["packages"][PKG]["placeholders"] = placeholders
    sheet = run(tmp_path, 70, [(PKG, 70, "")], menu=menu, probe=False)
    _assert_reason_items_in_order(
        line_of(sheet, "5 gal cambro").reasons,
        ["Coffee", "Decaf", "Hot water", "Iced water"] + expected_tail,
    )


def test_item_order_own_line_before_package(tmp_path, run, line_of):
    """Covers: AC-15 (right), §4.5-2. An item whose own line comes first is listed before the package's items."""
    sheet = run(tmp_path, 70, [("Iced water", 3, "Gallons"), (PKG, 3, "Gallons")], probe=False)
    _assert_reason_items_in_order(
        line_of(sheet, "5 gal cambro").reasons,
        ["Iced water", "Coffee", "Decaf", "Hot water", "Orange juice"],
    )


def test_item_order_package_before_own_line_of_later_item(tmp_path, run, line_of):
    """Covers: AC-15 (boundary), §4.5-2. Items first appearing on the package line stay in package order even if
    an own line for one of them comes later."""
    sheet = run(tmp_path, 70, [(PKG, 3, "Gallons"), ("Iced water", 3, "Gallons")], probe=False)
    _assert_reason_items_in_order(line_of(sheet, "5 gal cambro").reasons, ITEM_ORDER)


def test_item_order_in_item_and_unit_supply_reasons(tmp_path, rules_with, run, line_of):
    """Covers: AC-15 (right), AC-10, §4.5-6. Item names in a supply reason follow item order (Decaf listed first)."""
    rules = rules_with([{"supply": "Stir sticks", "qty": 1, "per": "item", "when_tagged": "COFFEE"}])
    sheet = run(tmp_path, 70, [("Decaf", 1, "Gallon"), ("Coffee", 1, "Gallon")], rules=rules, probe=False)
    reason = line_of(sheet, "Stir sticks").reasons[0]
    assert reason.index("Decaf") < reason.index("Coffee")

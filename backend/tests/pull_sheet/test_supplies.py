"""Add-ons, supplies, extras tiers, pull once, supply order (spec 002 §4.5 steps 4-7, EC-9, EC-17 to EC-19, EC-24).
Moved from tests/test_pull_sheet.py. Combining entries, ticks and reasons are in test_supply_combining.py;
cup count base and item order are in test_cup_count_and_order.py (split to keep files under 400 lines).

Shared helpers come from conftest.py as fixtures.
"""
import copy

import pytest

from pull_sheet import UNKNOWN_UNIT


# --------------------------------------------------------------------------
# AC-6: add-ons
# --------------------------------------------------------------------------
def test_ec9_addon_oatmilk(tmp_path, run, line_of):
    """Covers: AC-6 (right), AC-10, EC-9. Oatmilk 1 Each -> 'Oatmilk: 1', no cambro, reason from menu."""
    sheet = run(tmp_path, 70, [("Oatmilk", 1, "Each")], probe=False)
    line = line_of(sheet, "Oatmilk")
    assert line.quantity == 1
    assert len(line.reasons) == 1
    assert line.reasons[0].startswith("menu/beverages.json")
    assert "Oatmilk" in line.reasons[0]
    assert not [l for l in sheet.lines if "cambro" in l.supply]


@pytest.mark.parametrize("qty,expected", [("1.5", 2), ("2", 2), ("0.2", 1), ("2.01", 3)])
def test_addon_quantity_ceil(tmp_path, qty, expected, run, line_of):
    """Covers: AC-6 (boundary), NFR-2. Add-on quantity is ceil of the ordered amount."""
    sheet = run(tmp_path, 70, [("Oatmilk", qty, "Each")], probe=False)
    assert line_of(sheet, "Oatmilk").quantity == expected


def test_addon_own_lines_add_up(tmp_path, run, line_of):
    """Covers: AC-6 (right). Two Oatmilk lines are summed."""
    sheet = run(tmp_path, 70, [("Oatmilk", 1, "Each"), ("oatmilk", 2, "each")], probe=False)
    assert line_of(sheet, "Oatmilk").quantity == 3


def test_addon_order_follows_beo_and_precedes_supplies(tmp_path, default_menu, run, names):
    """Covers: AC-6 (right), §4.5-7. Add-ons in first-BEO-line order, after cambros, before supplies."""
    menu = default_menu()
    menu["items"]["Almond milk"] = {"unit": "each", "also_written_as": [], "tags": []}
    s1 = run(
        tmp_path, 70,
        [("Oatmilk", 1, "Each"), ("Coffee", 1, "Gallon"), ("Almond milk", 2, "Each")],
        menu=copy.deepcopy(menu), probe=False,
    )
    n = names(s1)
    assert n.index("1 gal cambro") < n.index("Oatmilk") < n.index("Almond milk") < n.index("hot-cups")
    s2 = run(
        tmp_path, 70,
        [("Almond milk", 2, "Each"), ("Oatmilk", 1, "Each")],
        menu=copy.deepcopy(menu), probe=False,
    )
    n2 = names(s2)
    assert n2.index("Almond milk") < n2.index("Oatmilk")


def test_each_item_with_wrong_units_skipped(tmp_path, run):
    """Covers: AC-6 (wrong), EC-10. Each item with Gallon or blank unit -> UNKNOWN_UNIT."""
    sheet = run(tmp_path, 70, [("Oatmilk", 1, "Gallon"), ("Oatmilk", 1, "")], probe=False)
    assert [s.problem for s in sheet.skipped] == [UNKNOWN_UNIT, UNKNOWN_UNIT]
    assert sheet.lines == ()


# --------------------------------------------------------------------------
# AC-7: supplies
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "guests,expected",
    [(1, 11), (20, 30), (21, 41), (50, 70), (51, 101), (100, 150), (101, 201), (120, 220)],
)
def test_ec17_extras_tiers(tmp_path, guests, expected, rules_with, run, qtys):
    """Covers: AC-7 (boundary), EC-17. guest+extra tier boundaries (inclusive upper bound)."""
    rules = rules_with([{"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"}],
                       extras=[
                           {"guests_up_to": 20, "extra": 10},
                           {"guests_up_to": 50, "extra": 20},
                           {"guests_up_to": 100, "extra": 50},
                           {"guests_up_to": None, "extra": 100},
                       ])
    sheet = run(tmp_path, guests, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["hot-cups"] == expected


def test_extras_tier_order_in_file_irrelevant(tmp_path, rules_with, run, qtys):
    """Covers: AC-7 (right), EC-17. The smallest guests_up_to >= guests wins regardless of file order."""
    rules = rules_with(
        [{"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"}],
        extras=[
            {"guests_up_to": None, "extra": 100},
            {"guests_up_to": 100, "extra": 50},
            {"guests_up_to": 20, "extra": 10},
            {"guests_up_to": 50, "extra": 20},
        ],
    )
    for guests, expected in [(20, 30), (21, 41), (101, 201)]:
        sheet = run(tmp_path, guests, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
        assert qtys(sheet)["hot-cups"] == expected


def test_extra_zero_allowed(tmp_path, rules_with, run, qtys):
    """Covers: AC-7 (boundary), §4.3. An extra of 0 is valid and adds nothing."""
    rules = rules_with(
        [{"supply": "Cups", "qty": 1, "per": "guest+extra"}],
        extras=[{"guests_up_to": None, "extra": 0}],
    )
    sheet = run(tmp_path, 30, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Cups"] == 30


def test_guest_plus_extra_qty_multiplies_guests_only(tmp_path, rules_with, run, qtys):
    """Covers: AC-7 (right). guest+extra = qty*guests + extra (extra not multiplied)."""
    rules = rules_with(
        [{"supply": "Cups", "qty": 2, "per": "guest+extra"}],
        extras=[{"guests_up_to": None, "extra": 7}],
    )
    sheet = run(tmp_path, 10, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Cups"] == 27


def test_ec18_hot_cups_once_for_many_hot_items(tmp_path, run, line_of, names):
    """Covers: AC-7 (right), EC-18. Coffee, Decaf, Hot water at 70 guests -> Hot cups 120, not 360."""
    sheet = run(
        tmp_path, 70,
        [("Coffee", 1, "Gallon"), ("Decaf", 1, "Gallon"), ("Hot water", 1, "Gallon")],
        probe=False,
    )
    line = line_of(sheet, "hot-cups")
    assert line.quantity == 120
    assert len(line.reasons) == 1
    assert line.reasons[0].startswith("rules/beverages.json supplies[0]")
    assert "cold-cups" not in names(sheet)


def test_ec18_both_hot_and_cold(tmp_path, run, qtys):
    """Covers: AC-7 (right), EC-18. Hot and cold ordered -> both cup lines, each guests + extra."""
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Iced water", 1, "Gallon")], probe=False)
    assert qtys(sheet)["hot-cups"] == 120
    assert qtys(sheet)["cold-cups"] == 120


def test_ec18_only_cold(tmp_path, run, names, qtys):
    """Covers: AC-7 (wrong), EC-18. Only cold ordered -> no Hot cups line."""
    sheet = run(tmp_path, 70, [("Iced water", 1, "Gallon")], probe=False)
    assert "hot-cups" not in names(sheet)
    assert qtys(sheet)["cold-cups"] == 120


def test_per_event(tmp_path, rules_with, run, qtys):
    """Covers: AC-7 (right), EC-19. event -> qty once, however many items match."""
    rules = rules_with([{"supply": "Pens", "qty": 3, "per": "event", "when_tagged": "HOT"}])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Decaf", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Pens"] == 3


def test_per_guest(tmp_path, rules_with, run, qtys):
    """Covers: AC-7 (right). guest -> qty * guests, once for several matching items."""
    rules = rules_with([{"supply": "Napkins", "qty": 2, "per": "guest", "when_tagged": "HOT"}])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Decaf", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Napkins"] == 140


def test_per_item(tmp_path, rules_with, run, line_of):
    """Covers: AC-7 (right). item -> qty * number of matching items (only tagged ones)."""
    rules = rules_with([{"supply": "Stir sticks", "qty": 2, "per": "item", "when_tagged": "COFFEE"}])
    sheet = run(
        tmp_path, 70,
        [("Coffee", 1, "Gallon"), ("Decaf", 1, "Gallon"), ("Hot water", 1, "Gallon")],
        rules=rules, probe=False,
    )
    line = line_of(sheet, "Stir sticks")
    assert line.quantity == 4
    assert line.reasons[0].startswith("rules/beverages.json supplies[0]")
    assert "Coffee" in line.reasons[0] and "Decaf" in line.reasons[0]
    assert "Hot water" not in line.reasons[0]


def test_per_item_no_tag_counts_all_ordered_items(tmp_path, rules_with, run, qtys):
    """Covers: AC-7 (right). item with no when_tagged counts every ordered item (gallon and each)."""
    rules = rules_with([{"supply": "Tags", "qty": 1, "per": "item"}])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Oatmilk", 1, "Each")], rules=rules, probe=False)
    assert qtys(sheet)["Tags"] == 2


def test_per_unit(tmp_path, rules_with, run, line_of):
    """Covers: AC-7 (right). unit -> sum over matching items of qty * ceil(ordered amount)."""
    rules = rules_with([{"supply": "Lids", "qty": 2, "per": "unit", "when_tagged": "HOT"}])
    sheet = run(
        tmp_path, 70,
        [("Coffee", "1.5", "Gallons"), ("Hot water", 1, "Gallon"), ("Iced water", 4, "Gallons")],
        rules=rules, probe=False,
    )
    line = line_of(sheet, "Lids")
    assert line.quantity == 2 * 2 + 2 * 1
    assert "Coffee" in line.reasons[0] and "Hot water" in line.reasons[0]
    assert "Iced water" not in line.reasons[0]


def test_ec24_tagged_rule_matches_each_item(tmp_path, default_menu, rules_with, run, line_of):
    """Covers: AC-7 (right), EC-24. Stir sticks 1 per item tagged coffee counts Oatmilk when it is tagged coffee."""
    menu = default_menu()
    menu["items"]["Oatmilk"]["tags"] = ["COFFEE"]
    rules = rules_with([{"supply": "Stir sticks", "qty": 1, "per": "item", "when_tagged": "COFFEE"}])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Oatmilk", 1, "Each")],
                menu=menu, rules=rules, probe=False)
    line = line_of(sheet, "Stir sticks")
    assert line.quantity == 2
    assert "Oatmilk" in line.reasons[0]


def test_supply_not_applied_when_no_matching_item(tmp_path, rules_with, run, names):
    """Covers: AC-7 (wrong). An entry with no matching ordered items contributes nothing."""
    rules = rules_with([{"supply": "Lids", "qty": 1, "per": "event", "when_tagged": "HOT"}])
    sheet = run(tmp_path, 70, [("Iced water", 1, "Gallon")], rules=rules, probe=False)
    assert "Lids" not in names(sheet)


def test_supply_order_matches_rules_order(tmp_path, run, names, qtys):
    """Covers: AC-7 (right), §4.5-7. Order: cambros, add-ons, supplies in rule order."""
    sheet = run(
        tmp_path, 70,
        [("Coffee", 1, "Gallons"), ("Iced water", 1, "Gallons"), ("Oatmilk", 1, "Each")],
        probe=False,
    )
    assert names(sheet) == [
        "1 gal cambro", "Oatmilk", "hot-cups", "cold-cups",
        "Cocktail napkins", "Creamer", "Stir sticks", "Sugar",
    ]
    assert qtys(sheet) == {
        "1 gal cambro": 2, "Oatmilk": 1, "hot-cups": 120, "cold-cups": 120,
        "Cocktail napkins": None, "Creamer": None, "Stir sticks": 1, "Sugar": 1,
    }


def test_ordered_item_without_matching_tags_gets_only_untagged_rules(tmp_path, run, names):
    """Covers: AC-7 (boundary). Iced water only: untagged rules apply, coffee-tagged ones do not."""
    sheet = run(tmp_path, 70, [("Iced water", 1, "Gallon")], probe=False)
    assert "Creamer" not in names(sheet)
    assert "Sugar" not in names(sheet)
    assert "Stir sticks" in names(sheet)

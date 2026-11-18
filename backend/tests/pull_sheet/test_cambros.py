"""Cambro choice (spec 002 §4.5 step 3, EC-14 to EC-16). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
import pytest


@pytest.mark.parametrize(
    "gallons,expected",
    [
        (1, [("1 gal cambro", 1)]),
        (3, [("5 gal cambro", 1)]),
        (5, [("5 gal cambro", 1)]),
        (6, [("5 gal cambro", 1), ("1 gal cambro", 1)]),
        (7, [("5 gal cambro", 1), ("2 gal cambro", 1)]),
        (8, [("5 gal cambro", 2)]),
        (12, [("5 gal cambro", 2), ("2 gal cambro", 1)]),
        (10, [("5 gal cambro", 2)]),
        (2, [("2 gal cambro", 1)]),
    ],
)
def test_cambro_selection(tmp_path, gallons, expected, run):
    """Covers: AC-5 (right/boundary), EC-14. Largest first, then smallest that holds the rest."""
    sheet = run(tmp_path, 70, [("Coffee", gallons, "Gallons")], probe=False)
    got = [(l.supply, l.quantity) for l in sheet.lines if "cambro" in l.supply]
    assert got == expected


def test_cambro_fractional_remainder_rounds_up_to_holding_cambro(tmp_path, run):
    """Covers: AC-5 (boundary). 5.5 gal -> 5 + smallest cambro holding 0.5 gal (1 gal)."""
    sheet = run(tmp_path, 70, [("Coffee", "5.5", "Gallons")], probe=False)
    got = [(l.supply, l.quantity) for l in sheet.lines if "cambro" in l.supply]
    assert got == [("5 gal cambro", 1), ("1 gal cambro", 1)]


def test_ec14_totals_reasons_and_order(tmp_path, run):
    """Covers: AC-5 (right), AC-10, EC-14. Coffee 7 + Hot water 2 -> 5 gal x1, 2 gal x2 (two reasons, coffee first)."""
    sheet = run(tmp_path, 70, [("Coffee", 7, "Gallons"), ("Hot water", 2, "Gallons")], probe=False)
    cambros = [l for l in sheet.lines if "cambro" in l.supply]
    assert [(l.supply, l.quantity) for l in cambros] == [("5 gal cambro", 1), ("2 gal cambro", 2)]
    five, two = cambros
    assert len(five.reasons) == 1
    assert five.reasons[0].startswith("rules/beverages.json cambros[0]")
    assert "Coffee" in five.reasons[0]
    assert len(two.reasons) == 2
    assert all(r.startswith("rules/beverages.json cambros[1]") for r in two.reasons)
    assert "Coffee" in two.reasons[0]
    assert "Hot water" in two.reasons[1]


def test_cambro_reason_order_follows_first_beo_line(tmp_path, run, line_of):
    """Covers: AC-5 (right), AC-10, EC-14. Reasons are ordered by each item's first BEO line."""
    sheet = run(tmp_path, 70, [("Hot water", 2, "Gallons"), ("Coffee", 7, "Gallons")], probe=False)
    two = line_of(sheet, "2 gal cambro")
    assert "Hot water" in two.reasons[0]
    assert "Coffee" in two.reasons[1]


def test_ec15_items_never_share_cambro(tmp_path, run, qtys):
    """Covers: AC-5 (wrong), EC-15. Coffee 1 gal + Decaf 1 gal -> two 1 gal cambros, never one 2 gal."""
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Decaf", 1, "Gallon")], probe=False)
    assert qtys(sheet)["1 gal cambro"] == 2
    assert "2 gal cambro" not in qtys(sheet)


def test_ec16_single_cambro_size(tmp_path, run, default_rules, qtys):
    """Covers: AC-5 (boundary), EC-16. Only a 3 gal cambro, 7 gal -> 3 + 3 + 3."""
    rules = default_rules()
    rules["cambros"] = [{"supply": "3 gal cambro", "gallons": 3}]
    sheet = run(tmp_path, 70, [("Coffee", 7, "Gallons")], rules=rules, probe=False)
    assert qtys(sheet)["3 gal cambro"] == 3
    assert len([l for l in sheet.lines if "cambro" in l.supply]) == 1


def test_cambro_listing_order_independent_of_config_order(tmp_path, run, default_rules):
    """Covers: AC-5 (right). Cambro lines are largest capacity first even if configured ascending."""
    rules = default_rules()
    rules["cambros"] = list(reversed(rules["cambros"]))
    sheet = run(tmp_path, 70, [("Coffee", 7, "Gallons")], rules=rules, probe=False)
    cambros = [l for l in sheet.lines if "cambro" in l.supply]
    assert [l.supply for l in cambros] == ["5 gal cambro", "2 gal cambro"]
    # reasons now point at the cambro's 0-based position in the file
    assert cambros[0].reasons[0].startswith("rules/beverages.json cambros[2]")
    assert cambros[1].reasons[0].startswith("rules/beverages.json cambros[1]")


def test_cambro_not_used_not_listed(tmp_path, run):
    """Covers: AC-5 (wrong). Only capacities actually used appear."""
    sheet = run(tmp_path, 70, [("Coffee", 5, "Gallons")], probe=False)
    assert [l.supply for l in sheet.lines if "cambro" in l.supply] == ["5 gal cambro"]


def test_each_item_gets_no_cambro(tmp_path, run):
    """Covers: AC-5 (wrong), AC-6. Each items never get a cambro."""
    sheet = run(tmp_path, 70, [("Oatmilk", 3, "Each")], probe=False)
    assert not [l for l in sheet.lines if "cambro" in l.supply]

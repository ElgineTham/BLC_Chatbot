"""Combining entries for one supply, ticks, exact arithmetic, first naming entry, reasons
(spec 002 §4.5 steps 5-7, EC-19 to EC-23, EC-32, AC-8, AC-10). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
import copy
import re

import pytest


# --------------------------------------------------------------------------
# AC-8: combining entries for one supply
# --------------------------------------------------------------------------
def test_ec19_sugar_two_entries_one_line(tmp_path, rules_with, run, names, line_of):
    """Covers: AC-8 (right), AC-10, EC-19. Two sugar entries -> one line, qty 1, two reasons in array order."""
    rules = rules_with([
        {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
        {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Hot water", 1, "Gallon")], rules=rules, probe=False)
    assert names(sheet).count("Sugar") == 1
    line = line_of(sheet, "Sugar")
    assert line.quantity == 1
    assert len(line.reasons) == 2
    assert line.reasons[0].startswith("rules/beverages.json supplies[0]")
    assert line.reasons[1].startswith("rules/beverages.json supplies[1]")


def test_ec19_only_one_entry_applies(tmp_path, rules_with, run, line_of):
    """Covers: AC-8 (boundary), EC-19. Only coffee ordered -> one reason (the second entry does not apply)."""
    rules = rules_with([
        {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
        {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    line = line_of(sheet, "Sugar")
    assert len(line.reasons) == 1
    assert line.reasons[0].startswith("rules/beverages.json supplies[0]")


def test_ec20_largest_contribution_wins(tmp_path, rules_with, run, line_of):
    """Covers: AC-8 (right), EC-20. 1/guest (coffee) and 1.5/guest (hot-water) at 100 guests -> 150, not 250."""
    rules = rules_with([
        {"supply": "Cups", "qty": 1, "per": "guest", "when_tagged": "COFFEE"},
        {"supply": "Cups", "qty": 1.5, "per": "guest", "when_tagged": "HOT-WATER"},
    ])
    sheet = run(tmp_path, 100, [("Coffee", 1, "Gallon"), ("Hot water", 1, "Gallon")], rules=rules, probe=False)
    line = line_of(sheet, "Cups")
    assert line.quantity == 150
    assert len(line.reasons) == 2


def test_largest_wins_when_larger_entry_listed_first(tmp_path, rules_with, run, qtys):
    """Covers: AC-8 (boundary), EC-20. Result is the maximum regardless of entry order."""
    rules = rules_with([
        {"supply": "Cups", "qty": 1.5, "per": "guest", "when_tagged": "HOT-WATER"},
        {"supply": "Cups", "qty": 1, "per": "guest", "when_tagged": "COFFEE"},
    ])
    sheet = run(tmp_path, 100, [("Coffee", 1, "Gallon"), ("Hot water", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Cups"] == 150


def test_ec21_creamer_tick_follows_tag(tmp_path, run, line_of, names):
    """Covers: AC-8 (right/wrong), EC-21. Creamer tick appears for coffee or decaf, not otherwise."""
    with_coffee = run(tmp_path, 70, [("Coffee", 1, "Gallon")], probe=False)
    with_decaf = run(tmp_path, 70, [("Decaf", 1, "Gallon")], probe=False)
    without = run(tmp_path, 70, [("Iced water", 1, "Gallon")], probe=False)
    assert line_of(with_coffee, "Creamer").quantity is None
    assert line_of(with_decaf, "Creamer").quantity is None
    assert "Creamer" not in names(without)


@pytest.mark.parametrize("variant", ["missing", "null"])
def test_ec22_napkins_untagged_tick(tmp_path, variant, default_rules, run, line_of):
    """Covers: AC-8 (right/wrong), EC-22. Untagged tick appears when anything is ordered, absent when all skipped."""
    rules = default_rules()
    if variant == "null":
        rules["supplies"][2]["when_tagged"] = None
    ordered = run(tmp_path, 70, [("Oatmilk", 1, "Each")], rules=copy.deepcopy(rules), probe=False)
    assert line_of(ordered, "Cocktail napkins").quantity is None
    nothing = run(tmp_path, 70, [("Cascade Breakfast", 70, "Packages"), ("Coffee", 1, "Each")],
                  rules=copy.deepcopy(rules), probe=False)
    assert nothing.lines == ()


def test_tick_line_reasons(tmp_path, run, line_of):
    """Covers: AC-8 (right), AC-10. A tick line carries a supplies[<i>] reason."""
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon")], probe=False)
    line = line_of(sheet, "Cocktail napkins")
    assert line.reasons and line.reasons[0].startswith("rules/beverages.json supplies[2]")


def test_two_tick_entries_same_supply_one_tick(tmp_path, rules_with, run, names, line_of):
    """Covers: AC-8 (right). Two tick entries for one supply -> one tick line, two reasons."""
    rules = rules_with([
        {"supply": "Creamer", "tick": True, "when_tagged": "COFFEE"},
        {"supply": "creamer", "tick": True, "when_tagged": "HOT-WATER"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Hot water", 1, "Gallon")], rules=rules, probe=False)
    assert names(sheet).count("Creamer") == 1
    line = line_of(sheet, "Creamer")
    assert line.quantity is None
    assert len(line.reasons) == 2


def test_display_name_from_first_entry(tmp_path, rules_with, run, names, line_of):
    """Covers: AC-8 (right). Display name is as written in the first entry naming the supply."""
    rules = rules_with([
        {"supply": "SUGAR  packets", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
        {"supply": "sugar packets", "qty": 2, "per": "event", "when_tagged": "HOT-WATER"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Hot water", 1, "Gallon")], rules=rules, probe=False)
    assert names(sheet) == ["1 gal cambro", "SUGAR  packets"]
    assert line_of(sheet, "SUGAR  packets").quantity == 2


def test_supply_line_position_is_first_appearance(tmp_path, rules_with, run, names, qtys):
    """Covers: AC-8 (right), §4.5-6. A merged supply sits where it first appears in supplies."""
    rules = rules_with([
        {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
        {"supply": "Forks", "qty": 1, "per": "event"},
        {"supply": "sugar", "qty": 3, "per": "event", "when_tagged": "HOT-WATER"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Hot water", 1, "Gallon")], rules=rules, probe=False)
    sup = [n for n in names(sheet) if "cambro" not in n]
    assert sup == ["Sugar", "Forks"]
    assert qtys(sheet)["Sugar"] == 3


def test_ec23_exact_arithmetic_point_one(tmp_path, rules_with, run, qtys):
    """Covers: AC-8 (boundary), EC-23, NFR-2. 0.1 per guest x 30 guests -> exactly 3 (float would give 4)."""
    rules = rules_with([{"supply": "Cups", "qty": 0.1, "per": "guest"}])
    sheet = run(tmp_path, 30, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Cups"] == 3


def test_exact_arithmetic_one_point_one(tmp_path, rules_with, run, qtys):
    """Covers: AC-8 (boundary), NFR-2. 1.1 per guest x 10 guests -> exactly 11 (float 11.000000000000002 would give 12)."""
    rules = rules_with([{"supply": "Cups", "qty": 1.1, "per": "guest"}])
    sheet = run(tmp_path, 10, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Cups"] == 11


def test_ec23_round_up_half(tmp_path, rules_with, run, qtys):
    """Covers: AC-8 (boundary), EC-23. 1.5 per guest x 33 = 49.5 -> 50."""
    rules = rules_with([{"supply": "Cups", "qty": 1.5, "per": "guest"}])
    sheet = run(tmp_path, 33, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert qtys(sheet)["Cups"] == 50


def test_quantities_are_ints_not_floats(tmp_path, run):
    """Covers: AC-8 (right), NFR-2. Numeric quantities are int (or None for ticks)."""
    sheet = run(tmp_path, 33, [("Coffee", 3, "Gallons"), ("Oatmilk", "1.5", "Each")])
    for l in sheet.lines:
        assert l.quantity is None or (isinstance(l.quantity, int) and not isinstance(l.quantity, bool))
        assert l.quantity is None or l.quantity >= 1


# --------------------------------------------------------------------------
# EC-32: first naming entry gives position and name
# --------------------------------------------------------------------------
def test_ec32_first_naming_entry_gives_position_and_name(tmp_path, rules_with, run, names, line_of):
    """Covers: AC-15 (right), EC-32, §4.5-6. supplies[0] `Cups` (COLD, not applying), [1] Sugar, [2] `cups` (HOT,
    applies): the sheet lists `Cups` (named as in supplies[0]) before Sugar, with one reason, supplies[2]."""
    rules = rules_with([
        {"supply": "Cups", "qty": 1, "per": "guest", "when_tagged": "COLD"},
        {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
        {"supply": "cups", "qty": 1, "per": "guest", "when_tagged": "HOT"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert names(sheet) == ["1 gal cambro", "Cups", "Sugar"]
    cups = line_of(sheet, "Cups")
    assert cups.quantity == 70
    assert len(cups.reasons) == 1
    assert cups.reasons[0].startswith("rules/beverages.json supplies[2]")


def test_ec32_no_entry_applies_means_no_line(tmp_path, rules_with, run, names):
    """Covers: AC-15 (wrong), EC-32. If no entry naming the supply applies, the supply does not appear."""
    rules = rules_with([
        {"supply": "Cups", "qty": 1, "per": "guest", "when_tagged": "COLD"},
        {"supply": "cups", "qty": 1, "per": "guest", "when_tagged": "TEA"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert names(sheet) == ["1 gal cambro"]


def test_ec32_tick_first_naming_entry(tmp_path, rules_with, run, names, line_of):
    """Covers: AC-15 (right), EC-32. A tick supply also takes name and position from its first naming entry."""
    rules = rules_with([
        {"supply": "Creamer", "tick": True, "when_tagged": "COLD"},
        {"supply": "Sugar", "qty": 1, "per": "event"},
        {"supply": "creamer", "tick": True, "when_tagged": "COFFEE"},
    ])
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon")], rules=rules, probe=False)
    assert names(sheet) == ["1 gal cambro", "Creamer", "Sugar"]
    assert line_of(sheet, "Creamer").quantity is None


# --------------------------------------------------------------------------
# AC-10: reasons
# --------------------------------------------------------------------------
def test_reason_prefixes(tmp_path, run, line_of):
    """Covers: AC-10 (right). Cambro, add-on and supply reasons use the documented prefixes."""
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon"), ("Oatmilk", 1, "Each")], probe=False)
    for l in sheet.lines:
        assert l.reasons, l.supply
    assert re.match(r"rules/beverages\.json cambros\[\d+\]", line_of(sheet, "1 gal cambro").reasons[0])
    assert line_of(sheet, "Oatmilk").reasons[0].startswith("menu/beverages.json")
    assert line_of(sheet, "hot-cups").reasons[0].startswith("rules/beverages.json supplies[0]")
    assert line_of(sheet, "Sugar").reasons[0].startswith("rules/beverages.json supplies[5]")
    assert line_of(sheet, "1 gal cambro").reasons[0].startswith("rules/beverages.json cambros[2]")


def test_reasons_are_tuple_of_str(tmp_path, run):
    """Covers: AC-10 (right). reasons is a tuple of strings on every line."""
    sheet = run(tmp_path, 70, [("Coffee", 1, "Gallon")], probe=False)
    for l in sheet.lines:
        assert isinstance(l.reasons, tuple)
        assert all(isinstance(r, str) for r in l.reasons)

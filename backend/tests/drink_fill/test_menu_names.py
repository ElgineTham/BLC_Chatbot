"""Spec 022, AC-1 (menu_names): EC-1 and EC-2. Unit tests on the Appendix A catalog."""
from __future__ import annotations

ITEMS = ["Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider", "Iced water",
         "Iced tea", "Orange juice", "Lemonade", "Peach tea", "Oatmilk"]


def test_ec1_spec_examples(names, PKG):
    """Covers: AC-1 (right), EC-1. Item, alias and package keys map to their display names."""
    assert names["decaf"] == "Decaf"
    assert names["fresh-brewed coffee"] == "Coffee"
    assert names["iced tea with lemon wedges"] == "Iced tea"
    assert names["coffee, decaf, tea, iced water & juice"] == PKG


def test_ec1_every_item_name_is_a_key_for_itself(names):
    """Covers: AC-1 (right), EC-1. Every menu item's own name (case-folded) maps to its display name."""
    for item in ITEMS:
        assert names[item.casefold()] == item


def test_ec1_other_aliases(names):
    """Covers: AC-1 (right), EC-1. Every also_written_as alias of Appendix A maps to its item."""
    assert names["fresh-brewed decaffeinated coffee"] == "Decaf"
    assert names["hot water with an assortment of black, green, and herbal tea bags"] == "Hot water"


def test_ec2_keys_are_casefolded_and_stripped(names):
    """Covers: AC-1 (right), EC-2. Each key is case-folded, stripped, with whitespace runs as one space."""
    assert names
    for key in names:
        assert key == key.casefold()
        assert key == " ".join(key.split())


def test_ec2_short_names_are_not_keys(names):
    """Covers: AC-1 (wrong), EC-2. 'tea', 'hot tea' and 'juice' are not keys; neither are plurals or misspellings."""
    for short in ("tea", "hot tea", "juice", "coffees", "decafe", "lemonades"):
        assert short not in names


def test_ec2_values_are_item_or_package_display_names(names, PKG):
    """Covers: AC-1 (right), EC-2. Every value is an item or package display name."""
    assert set(names.values()) <= set(ITEMS) | {PKG}
    assert set(names.values()) == set(ITEMS) | {PKG}


def test_menu_names_is_a_plain_dict_of_strings(names):
    """Covers: AC-1 (right). Returns dict[str, str]."""
    assert isinstance(names, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in names.items())


def test_menu_names_is_pure(catalog):
    """Covers: AC-1 (boundary), NFR-2. Calling twice gives equal results, and mutating one does not affect the next."""
    from blc.pull_sheet import menu_names

    a = menu_names(catalog)
    a.clear()
    b = menu_names(catalog)
    assert b["decaf"] == "Decaf"
    assert b == menu_names(catalog)

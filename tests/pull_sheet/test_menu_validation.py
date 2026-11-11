"""Menu file loading and errors (spec 002 §4.3 menu, EC-25, EC-33, EC-35). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
import pytest

from pull_sheet import MENU_FILE, RuleFileError, load_catalog

PKG = "Coffee, decaf, tea, iced water & juice"

MENU_BAD = {
    "unknown-include": lambda m: m["packages"][PKG]["includes"].append("Cofee"),
    "include-each-item": lambda m: m["packages"][PKG]["includes"].append("Oatmilk"),
    "package-equals-also-written-as": lambda m: m["packages"].update(
        {"Fresh-brewed coffee": {"includes": ["Coffee"]}}
    ),
    "placeholder-missing-tag": lambda m: m["packages"][PKG]["placeholders"].update(JUICE="Coffee"),
    "placeholder-default-not-item": lambda m: m["packages"][PKG]["placeholders"].update(
        JUICE="Mango juice"
    ),
    # Oatmilk gets the JUICE tag so that only the "names an each item" rule is broken.
    "placeholder-default-each-item": lambda m: (
        m["items"]["Oatmilk"].update(tags=["JUICE"]),
        m["packages"][PKG]["placeholders"].update(JUICE="Oatmilk"),
    ),
    "bad-unit": lambda m: m["items"]["Coffee"].update(unit="quart"),
    "unit-not-string": lambda m: m["items"]["Coffee"].update(unit=5),
    "misspelled-key": lambda m: (
        m["items"]["Coffee"].pop("also_written_as"),
        m["items"]["Coffee"].update(also_writen_as=[]),
    ),
    "missing-tags": lambda m: m["items"]["Coffee"].pop("tags"),
    "tags-string": lambda m: m["items"]["Coffee"].update(tags="HOT"),
    "item-name-clash": lambda m: m["items"].update(
        {"  COFFEE ": {"unit": "gallon", "also_written_as": [], "tags": []}}
    ),
    "alias-equals-other-item-name": lambda m: m["items"]["Decaf"].update(
        also_written_as=["coffee"]
    ),
    "alias-clash-across-items": lambda m: m["items"]["Decaf"].update(
        also_written_as=["FRESH-BREWED   coffee"]
    ),
    "alias-clash-within-item": lambda m: m["items"]["Coffee"].update(also_written_as=["a", "A"]),
    "package-key-equals-item": lambda m: m["packages"].update(
        {"coffee": {"includes": ["Coffee"]}}
    ),
    "package-duplicate-include": lambda m: m["packages"][PKG]["includes"].append("Coffee"),
    "package-empty": lambda m: (
        m["packages"][PKG].update(includes=[]),
        m["packages"][PKG].pop("placeholders"),
    ),
    "placeholder-default-duplicates-include": lambda m: (
        m["packages"][PKG]["includes"].append("Pomegranate juice"),
        m["packages"][PKG]["placeholders"].update(JUICE="Pomegranate juice"),
    ),
    "bad-tag-chars": lambda m: m["items"]["Coffee"].update(tags=["HOT_X"]),
    "lowercase-tag": lambda m: m["items"]["Coffee"].update(tags=["hot", "COFFEE"]),
    "mixed-case-tag": lambda m: m["items"]["Coffee"].update(tags=["Hot", "COFFEE"]),
    "empty-tag": lambda m: m["items"]["Coffee"].update(tags=[""]),
    "lowercase-placeholder-key": lambda m: m["packages"][PKG].update(
        placeholders={"juice": "Orange juice"}
    ),
    "bad-placeholder-tag": lambda m: m["packages"][PKG]["placeholders"].update(
        {"Bad Tag!": "Orange juice"}
    ),
    "empty-alias-string": lambda m: m["items"]["Coffee"].update(also_written_as=[""]),
    "empty-items": lambda m: (m.update(items={}), m.pop("packages")),
    "missing-items": lambda m: m.pop("items"),
    "unknown-top-key": lambda m: m.update(extra_key=1),
    "empty-item-name": lambda m: m["items"].update(
        {"  ": {"unit": "gallon", "also_written_as": [], "tags": []}}
    ),
    "unknown-package-key": lambda m: m["packages"][PKG].update(foo=1),
    "includes-missing": lambda m: m["packages"][PKG].pop("includes"),
}


@pytest.mark.parametrize("mutate", list(MENU_BAD.values()), ids=list(MENU_BAD.keys()))
def test_menu_errors(tmp_path, mutate, default_menu, write_dir):
    """Covers: AC-1 (wrong), EC-25, §4.3 (3, 5-8). Invalid menu -> RuleFileError on the menu file."""
    menu = default_menu()
    mutate(menu)
    base = write_dir(tmp_path, menu=menu)
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.path == base / MENU_FILE
    assert ei.value.line is None
    assert "beverages.json" in str(ei.value)


def test_menu_error_message_names_item(tmp_path, default_menu, write_dir):
    """Covers: NFR-5 (right), EC-35, AC-16. A bad item unit is located as items["Coffee"].unit (double quotes)."""
    menu = default_menu()
    menu["items"]["Coffee"]["unit"] = "quart"
    with pytest.raises(RuleFileError) as ei:
        load_catalog(write_dir(tmp_path, menu=menu))
    assert 'items["Coffee"].unit' in str(ei.value)
    assert "'Coffee'" not in str(ei.value)


def test_menu_error_message_names_package_include(tmp_path, default_menu, write_dir):
    """Covers: NFR-5 (right), AC-16, EC-25. Unknown include at index 1 is located with quoted package key and [1]."""
    menu = default_menu()
    menu["packages"][PKG]["includes"][1] = "Decafe"
    with pytest.raises(RuleFileError) as ei:
        load_catalog(write_dir(tmp_path, menu=menu))
    assert f'packages["{PKG}"].includes[1]' in str(ei.value)


def test_menu_valid_capital_tags_with_digits_and_hyphen(tmp_path, default_menu, make_catalog):
    """Covers: AC-1 (boundary), AC-16, §4.2. Capital tags with digits and hyphens are valid."""
    menu = default_menu()
    menu["items"]["Iced water"]["tags"] = ["COLD", "WATER-1", "0", "-"]
    assert make_catalog(tmp_path, menu) is not None


def test_lowercase_tag_is_error_not_a_different_tag(tmp_path, default_menu, write_dir):
    """Covers: AC-16 (wrong), EC-33. Menu tag `hot` is an error even though `HOT` exists; no case folding."""
    menu = default_menu()
    menu["items"]["Iced water"]["tags"] = ["hot"]
    with pytest.raises(RuleFileError) as ei:
        load_catalog(write_dir(tmp_path, menu=menu))
    assert ei.value.path.name == "beverages.json"
    assert ei.value.path == (tmp_path / "rules_dir" / MENU_FILE)

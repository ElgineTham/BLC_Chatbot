"""Catalog loading and rules file errors (spec 002 §4.3 rules, EC-25a, EC-25b, EC-26, EC-29).
Moved from tests/test_pull_sheet.py. Also holds the generic `load_catalog` tests (AC-1 there).

Shared helpers come from conftest.py as fixtures.
"""
import json

import pytest

from pull_sheet import (
    MENU_FILE,
    RULES_FILE,
    PullSheet,
    RuleFileError,
    build_pull_sheet,
    load_catalog,
)

PKG = "Coffee, decaf, tea, iced water & juice"


def test_load_valid_catalog_builds(tmp_path, make_catalog, mk_beo):
    """Covers: AC-1 (right). A valid dir loads and build_pull_sheet accepts it."""
    cat = make_catalog(tmp_path)
    sheet = build_pull_sheet(cat, mk_beo(70, [("Fresh-brewed coffee", 2, "Gallon")]))
    assert isinstance(sheet, PullSheet)
    assert sheet.guests == 70


def test_load_minimal_optional_keys_missing(
    tmp_path, default_menu, default_rules, make_catalog, mk_beo, names
):
    """Covers: AC-1 (right), EC-26 (boundary). packages, supplies, extras may be missing."""
    menu = default_menu()
    menu.pop("packages")
    rules = default_rules()
    rules.pop("supplies")
    rules.pop("extras")
    cat = make_catalog(tmp_path, menu, rules)
    sheet = build_pull_sheet(cat, mk_beo(10, [("Coffee", 1, "Gallon")]))
    assert names(sheet) == ["1 gal cambro"]


def test_load_package_without_placeholders(tmp_path, default_menu, make_catalog, mk_beo, qtys):
    """Covers: AC-1 (right), EC-26. placeholders may be missing from a package."""
    menu = default_menu()
    menu["packages"][PKG].pop("placeholders")
    cat = make_catalog(tmp_path, menu)
    sheet = build_pull_sheet(cat, mk_beo(70, [(PKG, 70, "")]))
    assert "5 gal cambro" in qtys(sheet)


def test_load_key_order_irrelevant(tmp_path, default_menu, default_rules, make_catalog, mk_beo):
    """Covers: AC-1 (right), EC-26. Key order inside objects does not matter."""
    menu = default_menu()
    rules = default_rules()
    rev_menu = {k: dict(reversed(list(v.items()))) for k, v in menu.items()}
    rev_rules = dict(reversed(list(rules.items())))
    cat = make_catalog(tmp_path, rev_menu, rev_rules)
    ref = make_catalog(tmp_path, default_menu(), default_rules())
    beo = mk_beo(70, [("Fresh-brewed coffee", 2, "Gallon")])
    assert build_pull_sheet(cat, beo) == build_pull_sheet(ref, beo)


def test_load_case_insensitive_unit_and_per(
    tmp_path, default_menu, default_rules, make_catalog, mk_beo, qtys
):
    """Covers: AC-1 (right). unit and per are case-insensitive."""
    menu = default_menu()
    menu["items"]["Coffee"]["unit"] = "Gallon"
    menu["items"]["Oatmilk"]["unit"] = "EACH"
    rules = default_rules()
    rules["supplies"][0]["per"] = "GUEST+Extra"
    cat = make_catalog(tmp_path, menu, rules)
    sheet = build_pull_sheet(cat, mk_beo(70, [("Coffee", 1, "Gallon")]))
    assert qtys(sheet)["hot-cups"] == 120


def test_load_when_tagged_null_equals_missing(tmp_path, default_rules, make_catalog, mk_beo, qtys):
    """Covers: AC-1 (right), EC-22. when_tagged null is accepted."""
    rules = default_rules()
    rules["supplies"][2]["when_tagged"] = None
    cat = make_catalog(tmp_path, None, rules)
    sheet = build_pull_sheet(cat, mk_beo(10, [("Coffee", 1, "Gallon")]))
    assert qtys(sheet)["Cocktail napkins"] is None


def test_load_ignores_other_files(tmp_path, write_dir):
    """Covers: AC-1 (right), EC-29. Other files in the rules dir are ignored."""
    base = write_dir(tmp_path)
    (base / "rules" / "food.json").write_text("{ this is not json", encoding="utf-8")
    (base / "menu" / "food.json").write_text("[[[", encoding="utf-8")
    (base / "README.txt").write_text("hello", encoding="utf-8")
    assert load_catalog(base) is not None


def test_load_missing_menu_file(tmp_path, write_dir, MISSING):
    """Covers: AC-1 (wrong), §4.3-1. Missing menu file -> RuleFileError with path."""
    base = write_dir(tmp_path, menu=MISSING)
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.path == base / MENU_FILE
    assert ei.value.line is None


def test_load_missing_rules_file(tmp_path, write_dir, MISSING):
    """Covers: AC-1 (wrong), §4.3-1. Missing rules file -> RuleFileError with path."""
    base = write_dir(tmp_path, rules=MISSING)
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.path == base / RULES_FILE


def test_load_missing_directory(tmp_path):
    """Covers: AC-1 (wrong), §4.3-1. A nonexistent directory -> RuleFileError."""
    with pytest.raises(RuleFileError):
        load_catalog(tmp_path / "nope")


@pytest.mark.parametrize("which", ["menu", "rules"])
def test_load_json_syntax_error_sets_line(tmp_path, which, write_dir):
    """Covers: AC-1 (wrong), EC-25b, NFR-5. Trailing comma -> RuleFileError.line = JSON error line."""
    bad = '{\n  "items": {\n    "a": 1,\n  }\n}\n'
    try:
        json.loads(bad)
    except json.JSONDecodeError as e:
        expected_line = e.lineno
    if which == "menu":
        base = write_dir(tmp_path, menu=bad)
        expected_path = base / MENU_FILE
    else:
        base = write_dir(tmp_path, rules=bad)
        expected_path = base / RULES_FILE
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.path == expected_path
    assert ei.value.line == expected_line
    assert str(expected_line) in str(ei.value)
    assert expected_path.name in str(ei.value)


def test_load_json_missing_quote_line(tmp_path, write_dir):
    """Covers: AC-1 (wrong), EC-25b. Missing quote -> line is set to the JSON error's line."""
    bad = '{\n  "cambros": [\n    {"supply: "x", "gallons": 1}\n  ]\n}\n'
    try:
        json.loads(bad)
    except json.JSONDecodeError as e:
        expected_line = e.lineno
    base = write_dir(tmp_path, rules=bad)
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.line == expected_line


@pytest.mark.parametrize("which", ["menu", "rules"])
def test_load_top_level_not_object(tmp_path, which, write_dir):
    """Covers: AC-1 (wrong), §4.3-3. A top-level JSON array is rejected, line is None."""
    base = write_dir(tmp_path, **{("menu" if which == "menu" else "rules"): "[]"})
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.path == base / (MENU_FILE if which == "menu" else RULES_FILE)
    assert ei.value.line is None


RULES_BAD = {
    "when-tagged-typo": lambda r: r["supplies"][0].update(when_tagged="HOT-DRNK"),
    "when-tagged-bad-chars": lambda r: r["supplies"][0].update(when_tagged="HOT_X"),
    "when-tagged-lowercase": lambda r: r["supplies"][0].update(when_tagged="hot"),
    "when-tagged-mixed-case": lambda r: r["supplies"][0].update(when_tagged="Hot"),
    "when-tagged-empty": lambda r: r["supplies"][0].update(when_tagged=""),
    "when-tagged-number": lambda r: r["supplies"][0].update(when_tagged=5),
    "tick-and-qty": lambda r: r["supplies"][2].update(qty=1),
    "tick-and-per": lambda r: r["supplies"][2].update(per="event"),
    "qty-without-per": lambda r: r["supplies"][4].pop("per"),
    "per-without-qty": lambda r: r["supplies"][4].pop("qty"),
    "neither-tick-nor-qty": lambda r: r["supplies"].append({"supply": "Forks"}),
    "tick-false": lambda r: r["supplies"][2].update(tick=False),
    "tick-string": lambda r: r["supplies"][2].update(tick="true"),
    "qty-zero": lambda r: r["supplies"][4].update(qty=0),
    "qty-negative": lambda r: r["supplies"][4].update(qty=-1),
    "qty-string": lambda r: r["supplies"][4].update(qty="1"),
    "qty-bool": lambda r: r["supplies"][4].update(qty=True),
    "per-invalid": lambda r: r["supplies"][4].update(per="weekly"),
    "per-not-string": lambda r: r["supplies"][4].update(per=1),
    "tick-and-numeric-same-supply": lambda r: r["supplies"].append(
        {"supply": "sugar", "tick": True}
    ),
    "numeric-and-tick-same-supply": lambda r: r["supplies"].append(
        {"supply": " CREAMER ", "qty": 1, "per": "event"}
    ),
    "supply-named-like-each-item": lambda r: r["supplies"].append(
        {"supply": "oatmilk", "tick": True}
    ),
    "supply-named-like-cambro": lambda r: r["supplies"].append(
        {"supply": "5 GAL  cambro", "tick": True}
    ),
    "two-null-extras": lambda r: r["extras"].append({"guests_up_to": None, "extra": 5}),
    "no-null-extra": lambda r: r["extras"].pop(),
    "guest-plus-extra-without-extras": lambda r: r.pop("extras"),
    "guest-plus-extra-empty-extras": lambda r: r.update(extras=[]),
    "duplicate-cambro-capacity": lambda r: r["cambros"].append({"supply": "other", "gallons": 2}),
    "duplicate-cambro-name": lambda r: r["cambros"].append({"supply": "5 gal cambro", "gallons": 3}),
    "missing-cambros": lambda r: r.pop("cambros"),
    "empty-cambros": lambda r: r.update(cambros=[]),
    "cambro-gallons-zero": lambda r: r["cambros"][0].update(gallons=0),
    "cambro-gallons-negative": lambda r: r["cambros"][0].update(gallons=-2),
    "cambro-gallons-string": lambda r: r["cambros"][0].update(gallons="5"),
    "cambro-missing-supply": lambda r: r["cambros"][0].pop("supply"),
    "misspelled-key": lambda r: (
        r["supplies"][0].pop("when_tagged"),
        r["supplies"][0].update(when_taged="HOT"),
    ),
    "duplicate-guests-up-to": lambda r: r["extras"].append({"guests_up_to": 50, "extra": 1}),
    "extra-negative": lambda r: r["extras"][0].update(extra=-1),
    "extra-fractional": lambda r: r["extras"][0].update(extra=1.5),
    "guests-up-to-zero": lambda r: r["extras"][0].update(guests_up_to=0),
    "guests-up-to-fractional": lambda r: r["extras"][0].update(guests_up_to=1.5),
    "unknown-top-key": lambda r: r.update(extra_key=1),
    "empty-supply-name": lambda r: r["supplies"][0].update(supply="  "),
    "supplies-not-list": lambda r: r.update(supplies={}),
}


@pytest.mark.parametrize("mutate", list(RULES_BAD.values()), ids=list(RULES_BAD.keys()))
def test_rules_errors(tmp_path, mutate, default_rules, write_dir):
    """Covers: AC-1 (wrong), EC-25a, §4.3 (3, 4, 9-15). Invalid rules -> RuleFileError on the rules file."""
    rules = default_rules()
    mutate(rules)
    base = write_dir(tmp_path, rules=rules)
    with pytest.raises(RuleFileError) as ei:
        load_catalog(base)
    assert ei.value.path == base / RULES_FILE
    assert ei.value.line is None
    assert "beverages.json" in str(ei.value)


def test_rules_error_message_names_entry(tmp_path, default_rules, write_dir):
    """Covers: NFR-5 (right), AC-1. A bad supplies entry is named by position in the message."""
    rules = default_rules()
    rules["supplies"][3]["when_tagged"] = "HOT-DRNK"
    with pytest.raises(RuleFileError) as ei:
        load_catalog(write_dir(tmp_path, rules=rules))
    assert "supplies[3]" in str(ei.value)


def test_rules_error_message_names_per_entry(tmp_path, default_rules, write_dir):
    """Covers: NFR-5 (right). Invalid per at supplies[1] mentions supplies[1]."""
    rules = default_rules()
    rules["supplies"][1]["per"] = "weekly"
    with pytest.raises(RuleFileError) as ei:
        load_catalog(write_dir(tmp_path, rules=rules))
    assert "supplies[1]" in str(ei.value)


def test_rules_error_message_location_per(tmp_path, default_rules, write_dir):
    """Covers: NFR-5 (right), EC-25a. An invalid per at supplies[4] is located as `supplies[4].per`."""
    rules = default_rules()
    rules["supplies"][4]["per"] = "weekly"
    with pytest.raises(RuleFileError) as ei:
        load_catalog(write_dir(tmp_path, rules=rules))
    assert "supplies[4].per" in str(ei.value)
    assert "beverages.json" in str(ei.value)


def test_rules_when_tagged_uppercase_valid(tmp_path, default_rules, make_catalog):
    """Covers: AC-16 (right), EC-33. when_tagged with a capital tag some item has is accepted."""
    rules = default_rules()
    rules["supplies"][0]["when_tagged"] = "HOT-WATER"
    assert make_catalog(tmp_path, None, rules) is not None

"""Spec 029 section 6.6 FILE (AC-11, AC-12, AC-13). Unit, plus one integration test on the real file."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from blc.tools.food_tools import (
    FOOD_RULES_FILE,
    FoodRulesError,
    calculate_food_item,
    load_food_rules,
)


def test_appendix_a_loads(write_rules, appendix_a):
    """Covers: AC-11 (right), FILE-1. Appendix A loads."""
    assert load_food_rules(write_rules(appendix_a)) is not None


def test_missing_file(tmp_path):
    """Covers: AC-11 (wrong), FILE-2. A missing file raises FoodRulesError."""
    with pytest.raises(FoodRulesError):
        load_food_rules(tmp_path / "nope.json")


@pytest.mark.parametrize("text", ["{", "", "[]", "{}"])
def test_bad_json_or_empty(write_rules, text):
    """Covers: AC-11 (wrong), FILE-2. Invalid JSON, empty file, non-object and {} raise."""
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(text))


def test_extras_empty(write_rules, appendix_a):
    """Covers: AC-11 (boundary), FILE-2. Empty extras."""
    appendix_a["extras"] = []
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


def test_napkins_empty(write_rules, appendix_a):
    """Covers: AC-11 (boundary), FILE-2. Empty napkins."""
    appendix_a["napkins"] = {}
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


@pytest.mark.parametrize("key", ["extras", "napkins"])
def test_missing_section(write_rules, appendix_a, key):
    """Covers: AC-11 (wrong), FILE-2. A missing extras or napkins key."""
    del appendix_a[key]
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


@pytest.mark.parametrize("extras", [
    [{"guests_up_to": 50, "extra": 20}, {"guests_up_to": 20, "extra": 10}, {"guests_up_to": None, "extra": 5}],
    [{"guests_up_to": 20, "extra": 10}, {"guests_up_to": 20, "extra": 12}, {"guests_up_to": None, "extra": 5}],
    [{"guests_up_to": 20, "extra": 10}, {"guests_up_to": 50, "extra": 20}],
    [{"guests_up_to": None, "extra": 10}, {"guests_up_to": None, "extra": 20}],
    [{"guests_up_to": None, "extra": 10}, {"guests_up_to": 50, "extra": 20}],
    [{"guests_up_to": 20, "extra": -1}, {"guests_up_to": None, "extra": 5}],
    [{"guests_up_to": 20}, {"guests_up_to": None, "extra": 5}],
])
def test_bad_extras(write_rules, appendix_a, extras):
    """Covers: AC-11 (wrong), FILE-3. Decreasing or repeated limits, last tier not null, early null,
    negative or missing extra."""
    appendix_a["extras"] = extras
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


def test_zero_extra_allowed(write_rules, appendix_a):
    """Covers: AC-11 (boundary). extra 0 is not negative, so it loads and gives count = guests."""
    appendix_a["extras"] = [{"guests_up_to": None, "extra": 0}]
    r = load_food_rules(write_rules(appendix_a))
    assert calculate_food_item("forks", guests=7, rules=r).count == 7


def test_meal_without_dinner_key(write_rules, appendix_a):
    """Covers: AC-11 (wrong), FILE-4. A meal lacking dinner."""
    appendix_a["napkins"]["lunch"] = {"cocktail": False}
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


def test_meal_without_cocktail_key(write_rules, appendix_a):
    """Covers: AC-11 (wrong), FILE-4. A meal lacking cocktail."""
    appendix_a["napkins"]["lunch"] = {"dinner": True}
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


@pytest.mark.parametrize("bad", ["yes", 1, None])
def test_non_boolean_napkin_value(write_rules, appendix_a, bad):
    """Covers: AC-11 (wrong), FILE-4. A non-boolean cocktail."""
    appendix_a["napkins"]["lunch"] = {"cocktail": bad, "dinner": True}
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_meal_name(write_rules, appendix_a, name):
    """Covers: AC-11 (wrong), FILE-4. A blank meal name."""
    appendix_a["napkins"][name] = {"cocktail": True, "dinner": False}
    with pytest.raises(FoodRulesError):
        load_food_rules(write_rules(appendix_a))


def test_changed_tiers_change_answers(write_rules, appendix_a):
    """Covers: AC-11 (right), FILE-5. Nothing is hard-coded to Appendix A's numbers."""
    appendix_a["extras"] = [{"guests_up_to": 10, "extra": 1}, {"guests_up_to": None, "extra": 2}]
    r = load_food_rules(write_rules(appendix_a))
    assert calculate_food_item("forks", guests=10, rules=r).count == 11
    assert calculate_food_item("forks", guests=11, rules=r).count == 13


def test_changed_napkin_table_changes_answers(write_rules, appendix_a):
    """Covers: AC-11 (right). Flipping the lunch row flips the answers."""
    appendix_a["napkins"]["lunch"] = {"cocktail": True, "dinner": False}
    r = load_food_rules(write_rules(appendix_a))
    assert calculate_food_item("cocktail napkins", meal="lunch", rules=r).answer is True
    assert calculate_food_item("dinner napkins", meal="lunch", rules=r).answer is False


def test_brunch_becomes_valid(write_rules, appendix_a):
    """Covers: AC-11 (right), FILE-6. A rules file with 'brunch' makes it valid."""
    appendix_a["napkins"]["brunch"] = {"cocktail": True, "dinner": False}
    r = load_food_rules(write_rules(appendix_a))
    res = calculate_food_item("cocktail napkins", meal="brunch", rules=r)
    assert res.status == "ok" and res.answer is True and res.meal == "brunch"


def test_meal_name_in_file_is_normalised(write_rules, appendix_a):
    """Covers: AC-11 (boundary). A file meal ' Brunch ' is canonical 'brunch'; lookups ignore case."""
    appendix_a["napkins"][" Brunch "] = {"cocktail": True, "dinner": False}
    r = load_food_rules(write_rules(appendix_a))
    res = calculate_food_item("cocktail napkins", meal="BRUNCH", rules=r)
    assert res.status == "ok" and res.meal == "brunch"


def test_tier_boundary_follows_file(write_rules, appendix_a):
    """Covers: AC-11 (boundary). guests equal to guests_up_to belongs to that tier."""
    appendix_a["extras"] = [{"guests_up_to": 5, "extra": 1}, {"guests_up_to": None, "extra": 9}]
    r = load_food_rules(write_rules(appendix_a))
    assert calculate_food_item("forks", guests=5, rules=r).count == 6
    assert calculate_food_item("forks", guests=6, rules=r).count == 15


def test_rules_none_with_missing_file_raises(point_rules_file_at_missing):
    """Covers: AC-12 (wrong), FILE-7. rules=None reads FOOD_RULES_FILE; a missing file raises."""
    with pytest.raises(FoodRulesError):
        calculate_food_item("forks", guests=70)


def test_load_default_path_missing_raises(point_rules_file_at_missing):
    """Covers: AC-11 (wrong), AC-12. load_food_rules() with no path uses FOOD_RULES_FILE."""
    with pytest.raises(FoodRulesError):
        load_food_rules()


def test_rules_file_constant():
    """Covers: AC-12 (right). FOOD_RULES_FILE is a Path ending in data/pull_sheet/rules/food.json."""
    assert isinstance(FOOD_RULES_FILE, Path)
    assert FOOD_RULES_FILE.parts[-4:] == ("data", "pull_sheet", "rules", "food.json")


def test_import_reads_no_file_and_skips_langchain():
    """Covers: AC-12 (right), FILE-8. Fresh interpreter: no langchain_core, no food.json read."""
    import blc
    src = str(Path(list(blc.__path__)[0]).parent)
    code = textwrap.dedent("""
        import builtins, io, sys, pathlib
        opened = []
        real_open = builtins.open
        def spy_open(f, *a, **k):
            opened.append(str(f))
            return real_open(f, *a, **k)
        builtins.open = spy_open
        for name in ("read_text", "read_bytes", "open"):
            orig = getattr(pathlib.Path, name)
            def make(orig):
                def wrapper(self, *a, **k):
                    opened.append(str(self))
                    return orig(self, *a, **k)
                return wrapper
            setattr(pathlib.Path, name, make(orig))
        import blc.tools.food_tools
        assert not any(m == "langchain_core" or m.startswith("langchain_core.") for m in sys.modules), "langchain_core imported"
        assert not any(p.endswith("food.json") for p in opened), opened
        print("OK")
    """)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={"PYTHONPATH": src, "PATH": ""}, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


@pytest.mark.integration
def test_real_file_values():
    """Covers: AC-13 (right), FILE-9. The real file gives 120, 201, True, False."""
    if not FOOD_RULES_FILE.exists():
        pytest.skip("real rules file not present")
    assert calculate_food_item("forks", guests=70).count == 120
    assert calculate_food_item("small plates", guests=101).count == 201
    assert calculate_food_item("dinner napkins", meal="Dinner").answer is True
    assert calculate_food_item("cocktail napkins", meal="lunch").answer is False


@pytest.mark.integration
def test_real_file_napkin_table():
    """Covers: AC-3 (right), AC-13. The real file's napkin table matches the spec."""
    if not FOOD_RULES_FILE.exists():
        pytest.skip("real rules file not present")
    for meal, cocktail in (("breakfast", True), ("reception", True), ("lunch", False), ("dinner", False)):
        assert calculate_food_item("cocktail napkins", meal=meal).answer is cocktail
        assert calculate_food_item("dinner napkins", meal=meal).answer is (not cocktail)

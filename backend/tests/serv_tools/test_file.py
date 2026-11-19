"""Spec 042 section 6.5 FILE (AC-9, AC-10, AC-11). Unit, plus integration on the real file."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from blc.tools.serv_tools import (
    SERV_RULES_FILE,
    SERV_TOOL_NAME,
    SERV_UTENSILS,
    ServRulesError,
    calculate_serving_utensils,
    load_serv_rules,
    run_serv_tool,
)


def food(appendix_a, name="butter croissants"):
    return appendix_a["foods"][name]


def croissants_result(rules, qty=3):
    return calculate_serving_utensils([("butter croissants", qty, None)], rules=rules)


def test_constants():
    """Covers: AC-9 (right). Names in the interface contract."""
    assert SERV_TOOL_NAME == "calculate_serving_utensils"
    assert len(SERV_UTENSILS) == 10 and SERV_UTENSILS[0] == "small tongs" and SERV_UTENSILS[-1] == "honey bear"


def test_appendix_a_loads(write_rules, appendix_a):
    """Covers: AC-9 (right), FILE-1. Appendix A loads."""
    assert load_serv_rules(write_rules(appendix_a)) is not None


def test_missing_file(tmp_path):
    """Covers: AC-9 (wrong), FILE-2. A missing file raises."""
    with pytest.raises(ServRulesError):
        load_serv_rules(tmp_path / "nope.json")


@pytest.mark.parametrize("text", ["{", "", "{}", '{"foods": {}}', '{"foods": null}'])
def test_bad_json_or_empty(write_rules, text):
    """Covers: AC-9 (wrong), FILE-2. Invalid JSON, empty file, no foods, empty foods."""
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(text))


def test_foods_key_removed(write_rules, appendix_a):
    """Covers: AC-9 (wrong), FILE-2. foods missing."""
    del appendix_a["foods"]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


@pytest.mark.parametrize("unit", ["pounds", "", None, 5])
def test_bad_unit(write_rules, appendix_a, unit):
    """Covers: AC-9 (wrong), FILE-3. unit not in SERV_UNITS."""
    food(appendix_a)["unit"] = unit
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_missing_unit(write_rules, appendix_a):
    """Covers: AC-9 (wrong), FILE-3. unit missing."""
    del food(appendix_a)["unit"]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_missing_utensils(write_rules, appendix_a):
    """Covers: AC-9 (wrong). utensils missing."""
    del food(appendix_a)["utensils"]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


@pytest.mark.parametrize("bad", ["small tongs", {"utensil": "small tongs"}, None, 3])
def test_utensils_not_list(write_rules, appendix_a, bad):
    """Covers: AC-9 (wrong). utensils must be a list."""
    food(appendix_a)["utensils"] = bad
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


@pytest.mark.parametrize("utensil", ["spork", "", None])
def test_bad_utensil_name(write_rules, appendix_a, utensil):
    """Covers: AC-9 (wrong), FILE-3. utensil not in SERV_UTENSILS."""
    food(appendix_a)["utensils"] = [{"utensil": utensil, "count": 1, "per": None}]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


@pytest.mark.parametrize("count", [0, 1.5, -1, "two"])
def test_bad_count(write_rules, appendix_a, count):
    """Covers: AC-9 (wrong), FILE-3. count must be a whole number >= 1."""
    food(appendix_a)["utensils"] = [{"utensil": "small tongs", "count": count, "per": 2}]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


@pytest.mark.parametrize("per", [0, -1, "ten", 0.0])
def test_bad_per(write_rules, appendix_a, per):
    """Covers: AC-9 (wrong), FILE-3. per must be null or a number > 0."""
    food(appendix_a)["utensils"] = [{"utensil": "small tongs", "count": 2, "per": per}]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_count_one_and_fractional_per_load(write_rules, appendix_a):
    """Covers: AC-9 (boundary). count 1 and per 0.5 are the smallest valid values."""
    food(appendix_a)["utensils"] = [{"utensil": "small tongs", "count": 1, "per": 0.5}]
    r = load_serv_rules(write_rules(appendix_a))
    # 3 dozen / 0.5 = 6 units, 1 each
    assert croissants_result(r, 3).utensils == {"small tongs": 6}


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_food_name(write_rules, appendix_a, name):
    """Covers: AC-9 (wrong), FILE-4. A blank food name."""
    appendix_a["foods"][name] = {"unit": "each", "aliases": [], "utensils": []}
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_blank_alias(write_rules, appendix_a):
    """Covers: AC-9 (wrong), FILE-4. A blank alias."""
    food(appendix_a)["aliases"].append("  ")
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_alias_equals_other_food_name_different_case(write_rules, appendix_a):
    """Covers: AC-9 (wrong), FILE-4. An alias equal to another food's name, ignoring case."""
    food(appendix_a)["aliases"].append("TRAIL MIX")
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_alias_equals_other_alias_ignoring_spaces(write_rules, appendix_a):
    """Covers: AC-9 (wrong), FILE-4. Two aliases equal ignoring case and spaces."""
    food(appendix_a)["aliases"].append("Deli  Sandwiches")
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_alias_equals_own_name(write_rules, appendix_a):
    """Covers: AC-9 (wrong), FILE-4. The same name twice across a food and its own alias."""
    food(appendix_a, "trail mix")["aliases"] = ["Trail Mix"]
    with pytest.raises(ServRulesError):
        load_serv_rules(write_rules(appendix_a))


def test_changed_per_and_count_change_answers(write_rules, appendix_a):
    """Covers: AC-9 (right), FILE-5. count 1, per 1: 3 dozen -> 3 tongs."""
    food(appendix_a)["utensils"] = [{"utensil": "small tongs", "count": 1, "per": 1}]
    assert croissants_result(load_serv_rules(write_rules(appendix_a))).utensils == {"small tongs": 3}


def test_changed_utensil_changes_answers(write_rules, appendix_a):
    """Covers: AC-9 (right). Swapping the utensil swaps the key."""
    food(appendix_a)["utensils"] = [{"utensil": "large tongs", "count": 2, "per": 2}]
    assert croissants_result(load_serv_rules(write_rules(appendix_a))).utensils == {"large tongs": 4}


def test_changed_unit_changes_answers(write_rules, appendix_a):
    """Covers: AC-9 (right). Croissants as an 'each' food: 24 -> 24 each, per 12, count 1 -> 2."""
    f = food(appendix_a)
    f["unit"] = "each"
    f["utensils"] = [{"utensil": "small tongs", "count": 1, "per": 12}]
    r = load_serv_rules(write_rules(appendix_a))
    assert croissants_result(r, 24).utensils == {"small tongs": 2}
    assert croissants_result(r, 25).utensils == {"small tongs": 3}


def test_new_food_in_file_is_known(write_rules, appendix_a):
    """Covers: AC-9 (right). A food added to the file is accepted by the tool."""
    appendix_a["foods"]["hummus"] = {"unit": "each", "aliases": ["Hummus Dip"],
                                     "utensils": [{"utensil": "ladle/sauce spoon", "count": 2}]}
    r = load_serv_rules(write_rules(appendix_a))
    res = run_serv_tool({"items": [{"food": "hummus dip", "qty": 4}]}, rules=r)
    assert res.status == "ok" and res.utensils == {"ladle/sauce spoon": 2} and res.foods == ("hummus",)


def test_count_left_out_is_one(write_rules, appendix_a):
    """Covers: AC-1 (right), AC-9 (right), FILE-6. count omitted: 1 per ceil(qty/per)."""
    food(appendix_a)["utensils"] = [{"utensil": "small tongs", "per": 2}]
    r = load_serv_rules(write_rules(appendix_a))
    assert croissants_result(r, 3).utensils == {"small tongs": 2}


def test_count_left_out_with_null_per(write_rules, appendix_a):
    """Covers: AC-1 (right), FILE-6. count omitted and per null: 1 per line."""
    food(appendix_a)["utensils"] = [{"utensil": "small tongs", "per": None}]
    r = load_serv_rules(write_rules(appendix_a))
    assert croissants_result(r, 30).utensils == {"small tongs": 1}


def test_rules_none_with_missing_file_raises(point_rules_file_at_missing):
    """Covers: AC-10 (wrong), FILE-7. rules=None reads SERV_RULES_FILE; missing file raises."""
    with pytest.raises(ServRulesError):
        calculate_serving_utensils([("trail mix", 1, None)])


def test_load_default_path_missing_raises(point_rules_file_at_missing):
    """Covers: AC-10 (wrong). load_serv_rules() with no path uses SERV_RULES_FILE."""
    with pytest.raises(ServRulesError):
        load_serv_rules()


def test_rules_file_constant():
    """Covers: AC-10 (right). SERV_RULES_FILE is a Path ending in data/pull_sheet/rules/serving_utensils.json."""
    assert isinstance(SERV_RULES_FILE, Path)
    assert SERV_RULES_FILE.parts[-4:] == ("data", "pull_sheet", "rules", "serving_utensils.json")


def test_import_reads_no_file_and_skips_langchain():
    """Covers: AC-10 (right), FILE-8. Fresh interpreter: no langchain_core, no serving_utensils.json read."""
    import blc
    src = str(Path(list(blc.__path__)[0]).parent)
    code = textwrap.dedent("""
        import builtins, sys, pathlib
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
        import blc.tools.serv_tools
        assert not any(m == "langchain_core" or m.startswith("langchain_core.") for m in sys.modules), "langchain_core imported"
        assert not any(p.endswith("serving_utensils.json") for p in opened), opened
        print("OK")
    """)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={"PYTHONPATH": src, "PATH": ""}, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


# Appendix B foods that must be known (names as in the confirmed table; match ignores case/punctuation).
REAL_FOODS = [
    ("breakfast muffins", "dozen"),
    ("butter croissants", "dozen"),
    ("fruit danish", "dozen"),
    ("assorted bagels", "dozen"),
    ("assorted scones", "dozen"),
    ("granola", "each"),
    ("fresh berries", "each"),
    ("vegan yogurt", "each"),
    ("classic deli sandwiches", "each"),
    ("quinoa-chickpea tabbouleh salad", "each"),
    ("trail mix", "bags"),
]


@pytest.mark.integration
def test_real_file_loads():
    """Covers: AC-11 (right), FILE-9. The real rules file loads."""
    if not SERV_RULES_FILE.exists():
        pytest.skip("real rules file not present")
    assert load_serv_rules() is not None


@pytest.mark.integration
@pytest.mark.parametrize("name,unit", REAL_FOODS)
def test_real_file_knows_foods(name, unit):
    """Covers: AC-11 (right), FILE-9. Appendix B foods are known (qty 1 in the food's own unit is not invalid)."""
    if not SERV_RULES_FILE.exists():
        pytest.skip("real rules file not present")
    r = calculate_serving_utensils([(name, 1, None)])
    assert r.status == "ok", r.text


@pytest.mark.integration
def test_real_file_values():
    """Covers: AC-11 (right), FILE-9. Appendix B numbers: croissants 3 dozen, deli 50, tabbouleh 3, trail mix."""
    if not SERV_RULES_FILE.exists():
        pytest.skip("real rules file not present")
    r = calculate_serving_utensils([("butter croissants", 3, None)])
    assert r.utensils == {"small tongs": 4, "spreader/knives": 2}
    r = calculate_serving_utensils([("classic deli sandwiches", 50, None)])
    assert r.utensils == {"large tongs": 6, "mayo/mustard": 2}
    r = calculate_serving_utensils([("quinoa-chickpea tabbouleh salad", 3, None)])
    assert r.utensils == {"salad tongs": 6}
    r = calculate_serving_utensils([("trail mix", 12, None)])
    assert r.status == "ok" and r.utensils == {}

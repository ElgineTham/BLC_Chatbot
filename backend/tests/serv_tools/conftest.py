"""Shared fixtures for spec 042 (serving utensils tool). Unit: the test rules (Appendix A) are written to tmp_path."""

from __future__ import annotations

import copy
import json
import sys

import pytest

from blc.tools.serv_tools import load_serv_rules, run_serv_tool

APPENDIX_A = {
    "foods": {
        "butter croissants": {
            "unit": "dozen",
            "aliases": ["Butter croissants served with raspberry preserves"],
            "utensils": [{"utensil": "small tongs", "count": 2, "per": 2}],
        },
        "assorted bagels": {
            "unit": "dozen",
            "aliases": ["bagels", "Assorted bagels with cream cheese"],
            "utensils": [
                {"utensil": "small tongs", "count": 1, "per": None},
                {"utensil": "spreader/knives", "count": 1, "per": None},
            ],
        },
        "classic deli sandwiches": {
            "unit": "each",
            "aliases": ["deli sandwiches"],
            "utensils": [
                {"utensil": "large tongs", "count": 1, "per": None},
                {"utensil": "mayo/mustard", "count": 1, "per": 25},
            ],
        },
        "quinoa-chickpea tabbouleh salad": {
            "unit": "each",
            "aliases": ["tabbouleh salad"],
            "utensils": [
                {"utensil": "salad tongs", "count": 1, "per": 1},
                {"utensil": "dressing/sauce bowl", "count": 1, "per": 1},
            ],
        },
        "yogurt with toppings": {
            "unit": "each",
            "aliases": [],
            "utensils": [
                {"utensil": "honey bear", "count": 2, "per": None},
                {"utensil": "serving spoon", "count": 2, "per": None},
                {"utensil": "serving spoon", "count": 2, "per": None},
            ],
        },
        "trail mix": {"unit": "bags", "aliases": [], "utensils": []},
    }
}


@pytest.fixture
def appendix_a():
    """A fresh, mutable copy of Appendix A as a dict."""
    return copy.deepcopy(APPENDIX_A)


@pytest.fixture
def write_rules(tmp_path):
    """write_rules(data_or_text, name="serv.json") -> Path. Dicts are dumped as JSON."""
    def _write(data, name="serv.json"):
        p = tmp_path / name
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p
    return _write


@pytest.fixture
def rules(write_rules, appendix_a):
    """The test rules: Appendix A, loaded."""
    return load_serv_rules(write_rules(appendix_a))


@pytest.fixture
def run(rules):
    """run(items) -> ServResult through run_serv_tool with the test rules."""
    def _run(items, **extra):
        return run_serv_tool({"items": items, **extra}, rules=rules)
    return _run


@pytest.fixture
def point_rules_file_at_missing(monkeypatch, tmp_path):
    """Patch SERV_RULES_FILE (in the package and every submodule that has it) to a missing path."""
    missing = tmp_path / "does_not_exist" / "serving_utensils.json"
    for name, mod in list(sys.modules.items()):
        if name.startswith("blc.tools.serv_tools") and mod is not None and hasattr(mod, "SERV_RULES_FILE"):
            monkeypatch.setattr(mod, "SERV_RULES_FILE", missing)
    return missing

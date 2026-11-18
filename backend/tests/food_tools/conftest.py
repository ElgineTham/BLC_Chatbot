"""Shared fixtures for spec 029 (food tool). Unit: the test rules (Appendix A) are written to tmp_path."""

from __future__ import annotations

import copy
import json
import sys

import pytest

from blc.tools.food_tools import load_food_rules

COUNT_ITEMS = ("spoons", "forks", "knives", "small plates", "large plates")
NAPKIN_ITEMS = ("cocktail napkins", "dinner napkins")

APPENDIX_A = {
    "extras": [
        {"guests_up_to": 20, "extra": 10},
        {"guests_up_to": 50, "extra": 20},
        {"guests_up_to": 100, "extra": 50},
        {"guests_up_to": None, "extra": 100},
    ],
    "napkins": {
        "breakfast": {"cocktail": True, "dinner": False},
        "reception": {"cocktail": True, "dinner": False},
        "lunch": {"cocktail": False, "dinner": True},
        "dinner": {"cocktail": False, "dinner": True},
    },
}


@pytest.fixture
def appendix_a():
    """A fresh, mutable copy of Appendix A as a dict."""
    return copy.deepcopy(APPENDIX_A)


@pytest.fixture
def write_rules(tmp_path):
    """write_rules(data_or_text, name="food.json") -> Path. Dicts are dumped as JSON."""
    def _write(data, name="food.json"):
        p = tmp_path / name
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p
    return _write


@pytest.fixture
def rules(write_rules, appendix_a):
    """The test rules: Appendix A, loaded."""
    return load_food_rules(write_rules(appendix_a))


@pytest.fixture
def point_rules_file_at_missing(monkeypatch, tmp_path):
    """Patch FOOD_RULES_FILE (in the package and every submodule that has it) to a missing path."""
    missing = tmp_path / "does_not_exist" / "food.json"
    for name, mod in list(sys.modules.items()):
        if name.startswith("blc.tools.food_tools") and mod is not None and hasattr(mod, "FOOD_RULES_FILE"):
            monkeypatch.setattr(mod, "FOOD_RULES_FILE", missing)
    return missing

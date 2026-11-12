"""Shared fixtures for spec 015 (recipe tool). Unit only: the test book is written to tmp_path."""

from __future__ import annotations

import copy
import json
from fractions import Fraction

import pytest

from blc.tools.recipe_tools import load_recipe_book

LEMONADE_STEPS = [
    "Pour the lemon concentrate into a clean container that holds the whole batch.",
    "Add water until the total volume reaches the batch size.",
    "Stir well until fully mixed.",
    "Taste and adjust if needed before service.",
]

LEMONADE = {
    "also_written_as": ["Fresh lemonade"],
    "yield_gallons": 1,
    "ingredients": [
        {"name": "Lemon concentrate", "amount": 7, "unit": "oz"},
        {"name": "Water", "fill": True},
    ],
    "steps": list(LEMONADE_STEPS),
}

FRUIT_PUNCH = {
    "also_written_as": ["Punch"],
    "yield_gallons": 2,
    "ingredients": [
        {"name": "Orange concentrate", "amount": 10, "unit": "oz"},
        {"name": "Simple syrup", "amount": 3, "unit": "oz"},
        {"name": "Water", "fill": True},
    ],
    "steps": [
        "Pour the orange concentrate and simple syrup into a clean container.",
        "Add water up to the batch size and stir.",
    ],
}


def appendix_a() -> dict:
    return {"recipes": {"Lemonade": copy.deepcopy(LEMONADE)}}


def appendix_ab() -> dict:
    data = appendix_a()
    data["recipes"]["Fruit punch"] = copy.deepcopy(FRUIT_PUNCH)
    return data


@pytest.fixture
def lemonade_steps():
    return list(LEMONADE_STEPS)


@pytest.fixture
def write_book(tmp_path):
    """write_book(data_or_text, name="recipes.json") -> Path. Dicts are dumped as JSON."""
    def _write(data, name="recipes.json"):
        p = tmp_path / name
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p
    return _write


@pytest.fixture
def book_a_data():
    return appendix_a()


@pytest.fixture
def book_ab_data():
    return appendix_ab()


@pytest.fixture
def book(write_book):
    """The test book: Appendix A + B."""
    return load_recipe_book(write_book(appendix_ab()))


@pytest.fixture
def F():
    return Fraction


@pytest.fixture
def ing():
    """ing(result) -> list of (name, amount, unit, fill) tuples."""
    def _ing(result):
        return [(i.name, i.amount, i.unit, i.fill) for i in result.ingredients]
    return _ing

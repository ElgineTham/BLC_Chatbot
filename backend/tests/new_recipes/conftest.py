"""Shared fixtures for spec 040 (new drink recipes, counted bags). Unit unless marked.

BAGS tests use a test book written to tmp_path. REAL tests use the real data/recipes/recipes.json and skip
when it is missing."""

from __future__ import annotations

import json
import urllib.request
from fractions import Fraction

import pytest

from blc.tools.recipe_tools import RECIPES_FILE, load_recipe_book


@pytest.fixture
def write_book(tmp_path):
    """write_book(data_or_text, name="recipes.json") -> Path."""
    def _write(data, name="recipes.json"):
        p = tmp_path / name
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p
    return _write


@pytest.fixture
def bag_book(write_book):
    """A test book with the two tea sizes of section 4.1."""
    data = {"recipes": {
        "Lemonade": {
            "yield_gallons": 1,
            "ingredients": [
                {"name": "Lemon concentrate", "amount": 7, "unit": "oz"},
                {"name": "Water", "fill": True},
            ],
            "steps": ["Pour the concentrate.", "Add water."],
        },
        "Test Iced Tea": {
            "also_written_as": ["Test tea"],
            "yield_gallons": 1,
            "ingredients": [
                {"bags": [
                    {"name": "3-gallon tea bag", "brews_from": 3, "brews_to": 4},
                    {"name": "1-gallon tea bag", "brews_from": 1, "brews_to": 1},
                ]},
                {"name": "Test syrup", "amount": 8, "unit": "oz"},
                {"name": "Water", "fill": True},
            ],
            "steps": [
                "Place the tea bags in a sanitized bucket.",
                "Add the syrup.",
                "Pour hot water to cover the tea bags and let steep for 10 minutes.",
                "Take out the spent bags and fill the rest with cold water to the batch size.",
            ],
        },
    }}
    return load_recipe_book(write_book(data))


@pytest.fixture
def real_book():
    """The real recipe book; skips when data/recipes/recipes.json does not exist."""
    if not RECIPES_FILE.exists():
        pytest.skip(f"{RECIPES_FILE} does not exist")
    return load_recipe_book(RECIPES_FILE)


@pytest.fixture
def F():
    return Fraction


@pytest.fixture
def ing():
    """ing(result) -> list of (name, amount, unit, fill) tuples."""
    def _ing(result):
        return [(i.name, i.amount, i.unit, i.fill) for i in result.ingredients]
    return _ing


def _ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def ollama_available():
    if not _ollama_running():
        pytest.skip("Ollama is not running.")
    return True


@pytest.fixture(scope="session")
def real_store(ollama_available):
    """The real Chroma store (read only); skips if it is missing."""
    from pathlib import Path

    from chat import CHROMA_DIR, build_store

    if not Path(CHROMA_DIR).exists():
        pytest.skip(f"Chroma store not found at {CHROMA_DIR}: run ingest.py first.")
    return build_store()

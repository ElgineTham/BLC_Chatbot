"""DOM: domain labels and ingest metadata (spec 028 section 6.1)."""

from __future__ import annotations

import pytest

from blc.retrieval import DOMAINS, OTHER_DOMAIN, domain_for
from domain_helpers import ROOT


def test_constants():
    """Covers: AC-1 (right). DOMAINS and OTHER_DOMAIN have the documented values."""
    assert tuple(DOMAINS) == ("food", "beverage")
    assert OTHER_DOMAIN == "other"


def test_food_file_is_food():
    """Covers: AC-1 (right), DOM-1. The food menu is labelled food."""
    assert domain_for("data/pull_sheet/menu/food.md") == "food"


@pytest.mark.parametrize(
    "source",
    ["data/pull_sheet/rules/beverages.md", "data/pull_sheet/menu/beverages.md"],
)
def test_beverage_menu_and_rules_are_beverage(source):
    """Covers: AC-1 (right), DOM-2. Beverage menu and rules are labelled beverage."""
    assert domain_for(source) == "beverage"


@pytest.mark.parametrize(
    "source",
    ["data/supplies/coffee.md", "data/recipes/lemonade.md", "data/supplies/syrups.md"],
)
def test_supplies_and_recipes_are_beverage(source):
    """Covers: AC-1 (right), DOM-3. Every supplies and recipes file is beverage."""
    assert domain_for(source) == "beverage"


def test_every_real_supply_and_recipe_file_is_beverage():
    """Covers: AC-1 (right). Each real data/supplies/*.md and data/recipes/*.md is beverage."""
    files = list((ROOT / "data" / "supplies").glob("*.md")) + list((ROOT / "data" / "recipes").glob("*.md"))
    assert files, "expected supplies/recipes files under data/"
    for f in files:
        assert domain_for(f.relative_to(ROOT).as_posix()) == "beverage", f


@pytest.mark.parametrize(
    "source",
    [
        "data/notes/other.md",
        "data/pull_sheet/menu/other.md",
        "data/pull_sheet/rules/food.md",
        "data/supplies/coffee.txt.bak",
        "food.md",
        "",
    ],
)
def test_other_paths_are_other(source):
    """Covers: AC-1 (wrong/boundary), DOM-4. Any path outside the named ones is other (including empty)."""
    assert domain_for(source) == "other"


@pytest.mark.integration
def test_ingest_food_chunks_labelled_food(tmp_store):
    """Covers: AC-2 (right), DOM-5. Every food.md chunk has domain food plus the existing keys."""
    from ingest import ingest_file

    path = ROOT / "data" / "pull_sheet" / "menu" / "food.md"
    n = ingest_file(tmp_store, path, path.stat().st_mtime)
    metas = tmp_store.get(include=["metadatas"])["metadatas"]
    assert n > 0 and len(metas) == n
    assert {m["domain"] for m in metas} == {"food"}
    for m in metas:
        for key in ("source", "category", "chunk_index"):
            assert key in m, f"missing {key}"
    assert {m["source"] for m in metas} == {"data/pull_sheet/menu/food.md"}


@pytest.mark.integration
def test_ingest_coffee_chunks_labelled_beverage(tmp_store):
    """Covers: AC-2 (right), DOM-6. Every supplies/coffee.md chunk has domain beverage plus existing keys."""
    from ingest import ingest_file

    path = ROOT / "data" / "supplies" / "coffee.md"
    n = ingest_file(tmp_store, path, path.stat().st_mtime)
    metas = tmp_store.get(include=["metadatas"])["metadatas"]
    assert n > 0 and len(metas) == n
    assert {m["domain"] for m in metas} == {"beverage"}
    for m in metas:
        for key in ("source", "category", "chunk_index"):
            assert key in m, f"missing {key}"

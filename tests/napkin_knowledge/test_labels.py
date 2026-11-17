"""LABEL: napkin domain constants and domain_for (spec 031 section 6.1)."""

from __future__ import annotations

import pytest

import blc.retrieval as retrieval
from blc.retrieval import DOMAINS, NAPKIN, OTHER_DOMAIN, domain_for


def test_constants():
    """Covers: AC-1 (right), LABEL-1. Constants have the documented values."""
    assert NAPKIN == "napkin"
    assert tuple(DOMAINS) == ("food", "beverage", "napkin")
    assert OTHER_DOMAIN == "other"
    assert retrieval.NAPKIN == "napkin"


def test_napkin_not_other():
    """Covers: AC-1 (wrong), LABEL-1. NAPKIN is a distinct domain from other."""
    assert NAPKIN != OTHER_DOMAIN
    assert OTHER_DOMAIN not in DOMAINS


@pytest.mark.parametrize(
    "source",
    ["data/pull_sheet/rules/napkins.md", "data\\pull_sheet\\rules\\napkins.md"],
)
def test_napkin_file_is_napkin(source):
    """Covers: AC-2 (right), LABEL-2. The napkin rules file (forward or back slashes) is napkin."""
    assert domain_for(source) == "napkin"


@pytest.mark.parametrize(
    "source,expected",
    [
        ("data/pull_sheet/menu/food.md", "food"),
        ("data/pull_sheet/menu/beverages.md", "beverage"),
        ("data/pull_sheet/rules/beverages.md", "beverage"),
        ("data/supplies/coffee.md", "beverage"),
        ("data/recipes/lemonade.md", "beverage"),
    ],
)
def test_existing_labels_unchanged(source, expected):
    """Covers: AC-2 (right), LABEL-3. Food, beverage, supplies and recipes files keep their labels."""
    assert domain_for(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        ("data/napkins.md", "other"),
        ("data/pull_sheet/rules/napkins.txt", "other"),
        ("data/pull_sheet/rules/napkins2.md", "other"),
        ("data/pull_sheet/menu/napkins.md", "other"),
        ("data/supplies/napkins.md", "beverage"),
    ],
)
def test_napkin_near_misses(source, expected):
    """Covers: AC-2 (wrong/boundary), LABEL-4. Near-miss paths are not napkin; supplies stays beverage."""
    assert domain_for(source) == expected
    assert domain_for(source) != "napkin"

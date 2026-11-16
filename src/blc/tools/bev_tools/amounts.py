"""Amounts per drink: own requests plus packages, larger one wins, in first-seen order."""

from __future__ import annotations

from fractions import Fraction

from blc.tools.bev_tools.catalog import Catalog
from blc.tools.bev_tools.catalog_entries import Package


def ordered_amounts(
    catalog: Catalog,
    own: dict[str, Fraction],
    first_own: dict[str, tuple[int, int]],
    package_lines: list[tuple[int, Package, Fraction]],
) -> tuple[dict[str, Fraction], dict[str, tuple[int, int]]]:
    tagged_own = {tag for name in own for tag in catalog._items[name].tags}
    pkg: dict[str, Fraction] = {}
    first = dict(first_own)

    def add(item: str, amount: Fraction, rank: tuple[int, int]) -> None:
        pkg[item] = pkg.get(item, Fraction(0)) + amount
        first[item] = min(first.get(item, rank), rank)

    for idx, package, amount in package_lines:
        position = 0
        for item in package.includes:
            add(item, amount, (idx, position))
            position += 1
        for tag, default in package.placeholders:
            if tag not in tagged_own:
                add(default, amount, (idx, position))
            position += 1
    ordered: dict[str, Fraction] = {}
    for item in sorted(set(own) | set(pkg)):
        best = max(own.get(item, Fraction(0)), pkg.get(item, Fraction(0)))
        if best > 0:
            ordered[item] = best
    return ordered, first

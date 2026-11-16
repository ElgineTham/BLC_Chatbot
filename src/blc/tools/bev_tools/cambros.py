"""Cambro choice (spec 002 section 4.5 step 3)."""

from __future__ import annotations

from fractions import Fraction

from blc.pull_sheet.catalog import Catalog
from blc.pull_sheet.constants import GALLON, RULES_FILE
from blc.pull_sheet.models import Cambro
from blc.pull_sheet.pull_line import PullLine


def _cambros_for(by_size: list[Cambro], amount: Fraction) -> list[Cambro]:
    largest = by_size[0]
    used: list[Cambro] = []
    remaining = amount
    while remaining >= largest.gallons:
        used.append(largest)
        remaining -= largest.gallons
    if remaining > 0:
        fits = [c for c in by_size if c.gallons >= remaining]
        used.append(min(fits, key=lambda c: c.gallons))
    return used


def cambro_lines(
    catalog: Catalog, ordered: dict[str, Fraction], order: list[str]
) -> list[PullLine]:
    by_size = sorted(catalog._cambros, key=lambda c: c.gallons, reverse=True)
    totals: dict[int, int] = {}
    reasons: dict[int, list[str]] = {}
    for item in order:
        if catalog._items[item].unit != GALLON:
            continue
        used = _cambros_for(by_size, ordered[item])
        for cambro in used:
            totals[cambro.index] = totals.get(cambro.index, 0) + 1
        for index in dict.fromkeys(c.index for c in used):
            reasons.setdefault(index, []).append(
                f"{RULES_FILE} cambros[{index}]: {item}"
            )
    return [
        PullLine(c.name, totals[c.index], tuple(reasons[c.index]))
        for c in by_size
        if c.index in totals
    ]

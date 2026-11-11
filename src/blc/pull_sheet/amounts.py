"""Matching BEO lines to the menu: packages, placeholders, item order, cup base."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from blc.pull_sheet.beo import Beo, BeoLine
from blc.pull_sheet.catalog import Catalog
from blc.pull_sheet.constants import EACH, GALLON, NOT_ON_MENU, UNKNOWN_UNIT
from blc.pull_sheet.models import Package
from blc.pull_sheet.text import guests_to_gallons, norm


@dataclass(frozen=True)
class Skipped:
    line: BeoLine
    problem: str


def _gallons_for(qty: Fraction, unit: str) -> Fraction | None:
    if unit == "":
        return guests_to_gallons(qty)
    if unit in ("gallon", "gallons"):
        return qty
    return None


def match_lines(
    catalog: Catalog, beo: Beo
) -> tuple[
    dict[str, Fraction],
    dict[str, tuple[int, int]],
    list[tuple[int, Package, Fraction]],
    list[Skipped],
    Fraction,
]:
    own: dict[str, Fraction] = {}
    first_own: dict[str, tuple[int, int]] = {}
    package_lines: list[tuple[int, Package, Fraction]] = []
    skipped: list[Skipped] = []
    base = Fraction(beo.guests)
    for idx, line in enumerate(beo.lines):
        hit = catalog._names.get(norm(line.name))
        if hit is None:
            skipped.append(Skipped(line, NOT_ON_MENU))
            continue
        kind, key = hit
        unit = norm(line.unit)
        if kind == "package" or catalog._items[key].unit == GALLON:
            amount = _gallons_for(line.qty, unit)
        else:
            amount = line.qty if unit == EACH else None
        if amount is None:
            skipped.append(Skipped(line, UNKNOWN_UNIT))
            continue
        if unit == "":
            base = max(base, line.qty)
        if kind == "package":
            package_lines.append((idx, catalog._packages[key], amount))
        else:
            own[key] = own.get(key, Fraction(0)) + amount
            first_own.setdefault(key, (idx, 0))
    return own, first_own, package_lines, skipped, base


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

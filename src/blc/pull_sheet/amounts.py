"""Matching BEO lines to the menu: packages, placeholders, item order, cup base."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from blc.pull_sheet.beo import Beo, BeoLine
from blc.pull_sheet.constants import NOT_ON_MENU, UNKNOWN_UNIT
from blc.tools.bev_tools import EACH, GALLON, Catalog, guests_to_gallons
from blc.tools.bev_tools.catalog_entries import Package
from blc.tools.bev_tools.names import norm


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

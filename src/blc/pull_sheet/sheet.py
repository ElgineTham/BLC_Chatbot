"""PullSheet and build_pull_sheet."""

from __future__ import annotations

import math
from dataclasses import dataclass

from blc.pull_sheet.amounts import Skipped, match_lines, ordered_amounts
from blc.pull_sheet.beo import Beo
from blc.pull_sheet.cambros import cambro_lines
from blc.pull_sheet.catalog import Catalog
from blc.pull_sheet.constants import EACH, MENU_FILE
from blc.pull_sheet.pull_line import PullLine
from blc.pull_sheet.supplies import supply_lines


@dataclass(frozen=True)
class PullSheet:
    guests: int
    lines: tuple[PullLine, ...]
    skipped: tuple[Skipped, ...]


def build_pull_sheet(catalog: Catalog, beo: Beo) -> PullSheet:
    """Pure function: compute the Beverages section for one BEO."""
    own, first_own, package_lines, skipped, base = match_lines(catalog, beo)
    ordered, first = ordered_amounts(catalog, own, first_own, package_lines)
    order = sorted(ordered, key=lambda n: first[n])

    lines = cambro_lines(catalog, ordered, order)
    for item in order:
        if catalog._items[item].unit == EACH:
            reason = (f"{MENU_FILE}: {item}",)
            lines.append(PullLine(item, math.ceil(ordered[item]), reason))
    lines.extend(supply_lines(catalog, base, ordered, order))
    return PullSheet(beo.guests, tuple(lines), tuple(skipped))

"""PullSheet and build_pull_sheet."""

from __future__ import annotations

from dataclasses import dataclass

from blc.pull_sheet.amounts import Skipped, match_lines
from blc.pull_sheet.beo import Beo
from blc.tools.bev_tools import Catalog, PullLine
from blc.tools.bev_tools.amounts import ordered_amounts
from blc.tools.bev_tools.item_lines import pull_lines


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

    lines = pull_lines(catalog, base, ordered, order)
    return PullSheet(beo.guests, tuple(lines), tuple(skipped))

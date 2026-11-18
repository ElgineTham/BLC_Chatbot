"""All pull lines for a set of ordered drinks: cambros, add-ons, supplies."""

from __future__ import annotations

import math
from fractions import Fraction

from blc.tools.bev_tools.cambros import cambro_lines
from blc.tools.bev_tools.catalog import MENU_FILE, Catalog
from blc.tools.bev_tools.catalog_entries import EACH
from blc.tools.bev_tools.pull_line import PullLine
from blc.tools.bev_tools.supplies import supply_lines


def pull_lines(
    catalog: Catalog, guests: Fraction | int, ordered: dict[str, Fraction], order: list[str]
) -> list[PullLine]:
    """Cambros, then each-items, then supplies; order is the drinks in first-seen order."""
    lines = cambro_lines(catalog, ordered, order)
    for item in order:
        if catalog._items[item].unit == EACH:
            reason = (f"{MENU_FILE}: {item}",)
            lines.append(PullLine(item, math.ceil(ordered[item]), reason))
    lines.extend(supply_lines(catalog, guests, ordered, order))
    return lines

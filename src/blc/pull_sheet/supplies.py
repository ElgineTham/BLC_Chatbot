"""Supply contributions, extras tiers and pull-once grouping (steps 4-7)."""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

from blc.pull_sheet.catalog import Catalog
from blc.pull_sheet.constants import RULES_FILE
from blc.pull_sheet.models import Supply
from blc.pull_sheet.pull_line import PullLine
from blc.pull_sheet.text import norm


def _extra_for(catalog: Catalog, guests: Fraction | int) -> int:
    tiers = sorted((b, e) for b, e in catalog._extras if b is not None)
    for bound, extra in tiers:
        if guests <= bound:
            return extra
    return next(e for b, e in catalog._extras if b is None)


def _contribution(
    catalog: Catalog,
    rule: Supply,
    guests: Fraction | int,
    ordered: dict[str, Fraction],
    matching: list[str],
) -> Fraction:
    qty = rule.qty
    assert qty is not None
    if rule.per == "event":
        return qty
    if rule.per == "guest":
        return qty * guests
    if rule.per == "guest+extra":
        return qty * guests + _extra_for(catalog, guests)
    if rule.per == "item":
        return qty * len(matching)
    return sum((qty * math.ceil(ordered[n]) for n in matching), Fraction(0))


def supply_lines(
    catalog: Catalog,
    guests: Fraction | int,
    ordered: dict[str, Fraction],
    order: list[str],
) -> list[PullLine]:
    groups: dict[str, dict[str, Any]] = {}
    for rule in catalog._supplies:
        group = groups.setdefault(
            norm(rule.name),
            {"name": rule.name, "tick": rule.tick, "values": [], "reasons": []},
        )
        matching = [
            n for n in order if rule.tag is None or rule.tag in catalog._items[n].tags
        ]
        if not matching:
            continue
        value: Fraction | None = None
        if not rule.tick:
            value = _contribution(catalog, rule, guests, ordered, matching)
        reason = f"{RULES_FILE} supplies[{rule.index}]"
        if rule.per in ("item", "unit"):
            reason += ": " + ", ".join(matching)
        if value is not None:
            group["values"].append(value)
        group["reasons"].append(reason)
    lines: list[PullLine] = []
    for group in groups.values():
        if not group["reasons"]:
            continue
        quantity = None if group["tick"] else math.ceil(max(group["values"]))
        lines.append(PullLine(group["name"], quantity, tuple(group["reasons"])))
    return lines

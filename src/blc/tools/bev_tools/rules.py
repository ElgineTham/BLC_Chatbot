"""Validation of rules/beverages.json."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from blc.pull_sheet.constants import EACH, PER_VALUES
from blc.pull_sheet.json_checks import Checker, is_int, is_number
from blc.pull_sheet.models import Cambro, Item, Supply
from blc.pull_sheet.text import norm

Extras = tuple[tuple[int | None, int], ...]


def _parse_cambros(chk: Checker, raw_cambros: list[Any]) -> list[Cambro]:
    if not raw_cambros:
        chk.fail("cambros", "must have at least one entry")
    cambros: list[Cambro] = []
    capacities: set[Fraction] = set()
    names: set[str] = set()
    for i, raw in enumerate(raw_cambros):
        where = f"cambros[{i}]"
        entry = chk.obj(where, raw, ("supply", "gallons"))
        name = chk.text(f"{where}.supply", entry["supply"])
        gallons = entry["gallons"]
        if not is_number(gallons) or gallons <= 0:
            chk.fail(f"{where}.gallons", "must be a number > 0")
        cap = Fraction(gallons)
        if cap in capacities:
            chk.fail(f"{where}.gallons", "duplicate cambro capacity")
        if norm(name) in names:
            chk.fail(f"{where}.supply", "duplicate cambro name")
        capacities.add(cap)
        names.add(norm(name))
        cambros.append(Cambro(i, name, cap))
    return cambros


def _parse_amount(chk: Checker, entry: dict[str, Any], where: str) -> tuple[Fraction, str]:
    if not is_number(entry["qty"]) or entry["qty"] <= 0:
        chk.fail(f"{where}.qty", "must be a number > 0")
    per_raw = entry["per"]
    per = per_raw.strip().casefold() if isinstance(per_raw, str) else None
    if per not in PER_VALUES:
        chk.fail(f"{where}.per", f"must be one of {', '.join(PER_VALUES)}")
    return Fraction(entry["qty"]), per


def _parse_supply(
    chk: Checker,
    i: int,
    raw: Any,
    blocked: set[str],
    all_tags: set[str],
    kinds: dict[str, bool],
) -> Supply:
    where = f"supplies[{i}]"
    entry = chk.obj(where, raw, ("supply",), ("qty", "per", "tick", "when_tagged"))
    name = chk.text(f"{where}.supply", entry["supply"])
    key = norm(name)
    if key in blocked:
        chk.fail(f"{where}.supply", "name equals a cambro or an 'each' item")
    has_tick = "tick" in entry
    if has_tick and entry["tick"] is not True:
        chk.fail(f"{where}.tick", "must be true when present")
    has_qty, has_per = "qty" in entry, "per" in entry
    if has_tick and (has_qty or has_per):
        chk.fail(where, "tick cannot be combined with qty/per")
    if not has_tick and not (has_qty and has_per):
        chk.fail(where, "needs either tick, or both qty and per")
    qty: Fraction | None = None
    per: str | None = None
    if not has_tick:
        qty, per = _parse_amount(chk, entry, where)
    tag: str | None = None
    if entry.get("when_tagged") is not None:
        tag = chk.tag(f"{where}.when_tagged", entry["when_tagged"])
        if tag not in all_tags:
            chk.fail(f"{where}.when_tagged", f"no item has tag {tag!r}")
    if key in kinds and kinds[key] != has_tick:
        chk.fail(where, "supply is a tick in one entry and numeric in another")
    kinds[key] = has_tick
    return Supply(i, name, qty, per, has_tick, tag)


def _parse_extras(chk: Checker, raw_extras: list[Any]) -> list[tuple[int | None, int]]:
    extras: list[tuple[int | None, int]] = []
    bounds: set[int | None] = set()
    for i, raw in enumerate(raw_extras):
        where = f"extras[{i}]"
        entry = chk.obj(where, raw, ("guests_up_to", "extra"))
        bound, extra = entry["guests_up_to"], entry["extra"]
        if bound is not None and (not is_int(bound) or bound <= 0):
            chk.fail(f"{where}.guests_up_to", "must be a positive integer or null")
        if not is_int(extra) or extra < 0:
            chk.fail(f"{where}.extra", "must be an integer >= 0")
        if bound in bounds:
            chk.fail(f"{where}.guests_up_to", "duplicate bound")
        bounds.add(bound)
        extras.append((bound, extra))
    if extras and None not in bounds:
        chk.fail("extras", "needs exactly one entry with guests_up_to null")
    return extras


def parse_rules(
    path: Path, data: Any, items: dict[str, Item]
) -> tuple[tuple[Cambro, ...], tuple[Supply, ...], Extras]:
    chk = Checker(path)
    top = chk.obj("rules", data, ("cambros",), ("supplies", "extras"))
    cambros = _parse_cambros(chk, chk.array("cambros", top["cambros"]))

    all_tags = {tag for item in items.values() for tag in item.tags}
    blocked = {norm(c.name) for c in cambros}
    blocked |= {norm(d) for d, it in items.items() if it.unit == EACH}
    kinds: dict[str, bool] = {}
    supplies = [
        _parse_supply(chk, i, raw, blocked, all_tags, kinds)
        for i, raw in enumerate(chk.array("supplies", top.get("supplies", [])))
    ]
    extras = _parse_extras(chk, chk.array("extras", top.get("extras", [])))
    if not extras and any(s.per == "guest+extra" for s in supplies):
        chk.fail("extras", "required because a supply uses guest+extra")
    return tuple(cambros), tuple(supplies), tuple(extras)

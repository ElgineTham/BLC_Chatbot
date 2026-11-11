"""Validation of menu/beverages.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from blc.pull_sheet.constants import EACH, GALLON
from blc.pull_sheet.json_checks import Checker, quote
from blc.pull_sheet.models import Item, Package
from blc.pull_sheet.text import norm

Names = dict[str, tuple[str, str]]


def _register(chk: Checker, names: Names, key: str, kind: str, display: str, where: str) -> None:
    if key in names:
        chk.fail(where, f"name clashes with {names[key][1]!r}")
    names[key] = (kind, display)


def _parse_item(chk: Checker, names: Names, raw_name: str, raw: Any) -> Item:
    where = f"items[{quote(raw_name)}]"
    display = chk.text(where, raw_name)
    entry = chk.obj(where, raw, ("unit", "also_written_as", "tags"))
    unit_raw = entry["unit"]
    if not isinstance(unit_raw, str) or unit_raw.strip().casefold() not in (GALLON, EACH):
        chk.fail(f"{where}.unit", "must be 'gallon' or 'each'")
    unit = unit_raw.strip().casefold()
    _register(chk, names, norm(display), "item", display, where)
    aliases = chk.array(f"{where}.also_written_as", entry["also_written_as"])
    for k, alias in enumerate(aliases):
        loc = f"{where}.also_written_as[{k}]"
        _register(chk, names, norm(chk.text(loc, alias)), "item", display, loc)
    raw_tags = chk.array(f"{where}.tags", entry["tags"])
    tags = frozenset(chk.tag(f"{where}.tags[{k}]", t) for k, t in enumerate(raw_tags))
    return Item(display, unit, tags)


def _resolve(
    chk: Checker, items: dict[str, Item], seen: set[str], value: Any, loc: str
) -> str:
    name = chk.text(loc, value)
    item = {norm(d): d for d in items}.get(norm(name))
    if item is None:
        chk.fail(loc, f"{name!r} is not an item")
    if items[item].unit != GALLON:
        chk.fail(loc, f"{name!r} is not a gallon item")
    if item in seen:
        chk.fail(loc, f"{name!r} appears twice in the package")
    seen.add(item)
    return item


def _parse_placeholders(
    chk: Checker, items: dict[str, Item], seen: set[str], raw_ph: Any, where: str
) -> list[tuple[str, str]]:
    if not isinstance(raw_ph, dict):
        chk.fail(f"{where}.placeholders", "must be an object")
    placeholders: list[tuple[str, str]] = []
    seen_tags: set[str] = set()
    for raw_tag, default in raw_ph.items():
        loc = f"{where}.placeholders[{quote(str(raw_tag))}]"
        tag = chk.tag(loc, raw_tag)
        if tag in seen_tags:
            chk.fail(loc, "duplicate placeholder tag")
        seen_tags.add(tag)
        item = _resolve(chk, items, seen, default, loc)
        if tag not in items[item].tags:
            chk.fail(loc, f"{item!r} does not have tag {tag!r}")
        placeholders.append((tag, item))
    return placeholders


def _parse_package(
    chk: Checker, items: dict[str, Item], display: str, raw: Any, where: str
) -> Package:
    entry = chk.obj(where, raw, ("includes",), ("placeholders",))
    seen: set[str] = set()
    raw_includes = chk.array(f"{where}.includes", entry["includes"])
    includes = tuple(
        _resolve(chk, items, seen, v, f"{where}.includes[{k}]")
        for k, v in enumerate(raw_includes)
    )
    placeholders = _parse_placeholders(
        chk, items, seen, entry.get("placeholders", {}), where
    )
    if not includes and not placeholders:
        chk.fail(where, "package includes nothing")
    return Package(display, includes, tuple(placeholders))


def parse_menu(
    path: Path, data: Any
) -> tuple[dict[str, Item], Names, dict[str, Package]]:
    chk = Checker(path)
    top = chk.obj("menu", data, ("items",), ("packages",))
    raw_items = top["items"]
    if not isinstance(raw_items, dict) or not raw_items:
        chk.fail("items", "must be an object with at least one entry")
    items: dict[str, Item] = {}
    names: Names = {}
    for raw_name, raw in raw_items.items():
        item = _parse_item(chk, names, raw_name, raw)
        items[item.display] = item

    packages: dict[str, Package] = {}
    raw_packages = top.get("packages", {})
    if not isinstance(raw_packages, dict):
        chk.fail("packages", "must be an object")
    for raw_name, raw in raw_packages.items():
        where = f"packages[{quote(raw_name)}]"
        display = chk.text(where, raw_name)
        _register(chk, names, norm(display), "package", display, where)
        packages[display] = _parse_package(chk, items, display, raw, where)
    return items, names, packages

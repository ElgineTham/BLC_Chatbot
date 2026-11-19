"""Turning the chat model's raw arguments into food lines (spec 042 4.3); no I/O."""

from __future__ import annotations

from collections.abc import Mapping

from blc.tools.serv_tools.calculator import calculate_serving_utensils
from blc.tools.serv_tools.reply_text import invalid_text
from blc.tools.serv_tools.result import ServResult
from blc.tools.serv_tools.rules import ServRules, load_serv_rules


def _invalid(problem: str) -> ServResult:
    return ServResult("invalid", invalid_text([problem]), None, None)


def _items(args: Mapping[str, object]) -> list[object] | None:
    items = args.get("items")
    if isinstance(items, Mapping):
        return [items]
    if isinstance(items, (list, tuple)) and items:
        return list(items)
    return None


def run_serv_tool(args: Mapping[str, object], rules: ServRules | None = None) -> ServResult:
    """Run the tool on a raw argument dict. Bad arguments give status "invalid"."""
    rules = rules if rules is not None else load_serv_rules()
    if not isinstance(args, Mapping):
        return _invalid('the arguments must be an object with "items"')
    items = _items(args)
    if items is None:
        return _invalid('"items" must be a non-empty list of objects')
    lines: list[tuple[object, object, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            return _invalid(f"each item must be an object, not {item!r}")
        lines.append((item.get("food"), item.get("qty"), item.get("unit")))
    return calculate_serving_utensils(lines, rules)  # type: ignore[arg-type]

"""Raw argument parsing for the Always items tool (spec 044)."""

from __future__ import annotations

from collections.abc import Mapping

from blc.tools.always_tools.counting import build_result
from blc.tools.always_tools.reply_text import invalid_text
from blc.tools.always_tools.result import AlwaysResult
from blc.tools.always_tools.scopes import parse_scope, scope_fields

FIELDS: tuple[str, ...] = ("tables", "drip_trays")


class _Bad:
    """Marker for a value that is not a valid whole number."""


_BAD = _Bad()


def _parse(value: object) -> int | None | _Bad:
    if value is None or isinstance(value, bool):
        return None if value is None else _BAD
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return _BAD
        return _from_number(number)
    if isinstance(value, (int, float)):
        return _from_number(value)
    return _BAD


def _from_number(number: float) -> int | _Bad:
    if number != number or number in (float("inf"), float("-inf")) or number != int(number):
        return _BAD
    return int(number)


def run_always_tool(args: Mapping[str, object]) -> AlwaysResult:
    if not isinstance(args, Mapping):
        return AlwaysResult("invalid", invalid_text([]), None, None)
    about = parse_scope(args.get("about"))
    parsed = {name: _parse(args.get(name)) for name in scope_fields(about)}
    bad = tuple(name for name, value in parsed.items() if isinstance(value, _Bad))
    values = {name: (None if isinstance(v, _Bad) else v) for name, v in parsed.items()}
    return build_result(values.get("tables"), values.get("drip_trays"), bad, about)

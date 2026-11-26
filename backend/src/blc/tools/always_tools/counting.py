"""Counts for the Always box (spec 044); no I/O."""

from __future__ import annotations

from blc.tools.always_tools.reply_text import invalid_text, need_info_text, ok_text
from blc.tools.always_tools.result import (
    ALWAYS_CHECK_ITEMS,
    ALWAYS_COUNT_ORDER,
    ALWAYS_WHITE_LINENS,
    AlwaysResult,
)
from blc.tools.always_tools.scopes import DEFAULT_SCOPE, parse_scope, scope_fields

BLACK_LINENS_PER_TABLE = 2
BLACK_LINENS_EXTRA = 1  # added once when there is at least one table
PURPLE_NAPKINS_PER_TABLE = 2
BLACK_NAPKINS_PER_DRIP_TRAY = 1


def _linens(number: int) -> int:
    return number * BLACK_LINENS_PER_TABLE + BLACK_LINENS_EXTRA if number >= 1 else 0


def count_items(
    tables: int | None, drip_trays: int | None, white_tables: int | None = None
) -> dict[str, int]:
    """The items whose number is known, in ALWAYS_COUNT_ORDER order."""
    values: dict[str, int] = {}
    if tables is not None:
        values["black linens"] = _linens(tables)
    if white_tables is not None:
        values[ALWAYS_WHITE_LINENS] = _linens(white_tables)
    if tables is not None or white_tables is not None:
        values["purple napkins"] = ((tables or 0) + (white_tables or 0)) * PURPLE_NAPKINS_PER_TABLE
    if drip_trays is not None:
        values["black napkins"] = drip_trays * BLACK_NAPKINS_PER_DRIP_TRAY
    return {item: values[item] for item in ALWAYS_COUNT_ORDER if item in values}


def build_result(
    tables: int | None,
    drip_trays: int | None,
    invalid_fields: tuple[str, ...] = (),
    about: str = DEFAULT_SCOPE,
    white_tables: int | None = None,
) -> AlwaysResult:
    """Precedence: invalid, then need_info, then ok. Fields outside `about` are ignored."""
    fields = scope_fields(about)
    given = {
        name: value
        for name, value in (("tables", tables), ("white_tables", white_tables), ("drip_trays", drip_trays))
        if name in fields
    }
    bad = [name for name, value in given.items() if name in invalid_fields or (value is not None and value < 0)]
    if bad:
        return AlwaysResult("invalid", invalid_text(bad), None, None)
    counts = count_items(given.get("tables"), given.get("drip_trays"), given.get("white_tables"))
    missing = []
    if "tables" in given and given["tables"] is None and given.get("white_tables") is None:
        missing.append("tables")
    if "drip_trays" in given and given["drip_trays"] is None:
        missing.append("drip_trays")
    if missing:
        return AlwaysResult("need_info", need_info_text(counts, missing), ALWAYS_CHECK_ITEMS, counts)
    return AlwaysResult("ok", ok_text(counts), ALWAYS_CHECK_ITEMS, counts)


def calculate_always_items(
    tables: int | None,
    drip_trays: int | None,
    about: str = DEFAULT_SCOPE,
    white_tables: int | None = None,
) -> AlwaysResult:
    return build_result(tables, drip_trays, (), parse_scope(about), white_tables)

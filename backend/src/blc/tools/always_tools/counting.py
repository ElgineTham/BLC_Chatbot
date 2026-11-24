"""Counts for the Always box (spec 044); no I/O."""

from __future__ import annotations

from blc.tools.always_tools.reply_text import invalid_text, need_info_text, ok_text
from blc.tools.always_tools.result import (
    ALWAYS_CHECK_ITEMS,
    ALWAYS_COUNT_ITEMS,
    AlwaysResult,
)
from blc.tools.always_tools.scopes import DEFAULT_SCOPE, parse_scope, scope_fields

BLACK_LINENS_PER_TABLE = 2
BLACK_LINENS_EXTRA = 1  # added once when there is at least one table
PURPLE_NAPKINS_PER_TABLE = 2
BLACK_NAPKINS_PER_DRIP_TRAY = 1


def count_items(tables: int | None, drip_trays: int | None) -> dict[str, int]:
    """The items whose number is known, in ALWAYS_COUNT_ITEMS order."""
    values: dict[str, int] = {}
    if tables is not None:
        linens = tables * BLACK_LINENS_PER_TABLE + BLACK_LINENS_EXTRA if tables >= 1 else 0
        values["black linens"] = linens
        values["purple napkins"] = tables * PURPLE_NAPKINS_PER_TABLE
    if drip_trays is not None:
        values["black napkins"] = drip_trays * BLACK_NAPKINS_PER_DRIP_TRAY
    return {item: values[item] for item in ALWAYS_COUNT_ITEMS if item in values}


def build_result(
    tables: int | None,
    drip_trays: int | None,
    invalid_fields: tuple[str, ...] = (),
    about: str = DEFAULT_SCOPE,
) -> AlwaysResult:
    """Precedence: invalid, then need_info, then ok. Fields outside `about` are ignored."""
    fields = scope_fields(about)
    given = {name: value for name, value in (("tables", tables), ("drip_trays", drip_trays)) if name in fields}
    bad = [name for name, value in given.items() if name in invalid_fields or (value is not None and value < 0)]
    if bad:
        return AlwaysResult("invalid", invalid_text(bad), None, None)
    counts = count_items(given.get("tables"), given.get("drip_trays"))
    missing = [name for name, value in given.items() if value is None]
    if missing:
        return AlwaysResult("need_info", need_info_text(counts, missing), ALWAYS_CHECK_ITEMS, counts)
    return AlwaysResult("ok", ok_text(counts), ALWAYS_CHECK_ITEMS, counts)


def calculate_always_items(
    tables: int | None, drip_trays: int | None, about: str = DEFAULT_SCOPE
) -> AlwaysResult:
    return build_result(tables, drip_trays, (), parse_scope(about))

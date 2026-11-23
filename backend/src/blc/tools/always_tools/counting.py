"""Counts for the Always box (spec 044); no I/O."""

from __future__ import annotations

from blc.tools.always_tools.reply_text import invalid_text, need_info_text, ok_text
from blc.tools.always_tools.result import (
    ALWAYS_CHECK_ITEMS,
    ALWAYS_COUNT_ITEMS,
    AlwaysResult,
)

BLACK_LINENS_PER_TABLE = 2
BLACK_LINENS_EXTRA = 1  # added once when there is at least one table
PURPLE_NAPKINS_PER_TABLE = 2
BLACK_NAPKINS_PER_DRIP_TRAY = 1


def count_items(tables: int, drip_trays: int) -> dict[str, int]:
    linens = tables * BLACK_LINENS_PER_TABLE + BLACK_LINENS_EXTRA if tables >= 1 else 0
    values = {
        "black linens": linens,
        "black napkins": drip_trays * BLACK_NAPKINS_PER_DRIP_TRAY,
        "purple napkins": tables * PURPLE_NAPKINS_PER_TABLE,
    }
    return {item: values[item] for item in ALWAYS_COUNT_ITEMS}


def build_result(
    tables: int | None, drip_trays: int | None, invalid_fields: tuple[str, ...] = ()
) -> AlwaysResult:
    """Precedence: invalid, then need_info, then ok. `invalid_fields` are already-bad fields."""
    given = {"tables": tables, "drip_trays": drip_trays}
    bad = [name for name in given if name in invalid_fields]
    bad += [n for n, v in given.items() if n not in bad and v is not None and v < 0]
    bad.sort(key=list(given).index)
    if bad:
        return AlwaysResult("invalid", invalid_text(bad), None, None)
    missing = [name for name, value in given.items() if value is None]
    if missing:
        return AlwaysResult("need_info", need_info_text(missing), None, None)
    counts = count_items(tables, drip_trays)  # type: ignore[arg-type]
    return AlwaysResult("ok", ok_text(counts), ALWAYS_CHECK_ITEMS, counts)


def calculate_always_items(tables: int | None, drip_trays: int | None) -> AlwaysResult:
    return build_result(tables, drip_trays)

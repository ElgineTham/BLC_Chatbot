"""Constants and the result type of the Always items tool (spec 044)."""

from __future__ import annotations

from dataclasses import dataclass

ALWAYS_TOOL_NAME = "calculate_always_items"
ALWAYS_CHECK_ITEMS: tuple[str, ...] = ("bus tubs", "towels")
ALWAYS_COUNT_ITEMS: tuple[str, ...] = ("black linens", "black napkins", "purple napkins")
ALWAYS_STATUSES: tuple[str, ...] = ("ok", "need_info", "invalid")


@dataclass(frozen=True)
class AlwaysResult:
    status: str
    text: str
    checks: tuple[str, ...] | None
    counts: dict[str, int] | None

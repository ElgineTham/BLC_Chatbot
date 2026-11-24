"""Which Always items a question is about (spec 045); no I/O."""

from __future__ import annotations

ALWAYS_SCOPES: tuple[str, ...] = ("tables", "drip_trays", "both")
ALWAYS_TABLE_ITEMS: tuple[str, ...] = ("black linens", "purple napkins")
ALWAYS_DRIP_TRAY_ITEMS: tuple[str, ...] = ("black napkins",)
DEFAULT_SCOPE = "both"


def parse_scope(value: object) -> str:
    """Case and spaces ignored, "drip trays" accepted; anything else is "both"."""
    if not isinstance(value, str):
        return DEFAULT_SCOPE
    text = value.strip().lower().replace(" ", "_")
    return text if text in ALWAYS_SCOPES else DEFAULT_SCOPE


def scope_fields(about: str) -> tuple[str, ...]:
    """The number fields a scope asks about, in tables, drip_trays order."""
    if about == "tables":
        return ("tables",)
    if about == "drip_trays":
        return ("drip_trays",)
    return ("tables", "drip_trays")

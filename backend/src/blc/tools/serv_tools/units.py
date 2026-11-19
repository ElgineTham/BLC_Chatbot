"""Unit names and each/dozen conversion (spec 042 4.2); no I/O."""

from __future__ import annotations

PER_DOZEN = 12
_UNIT_NAMES = {
    "each": "each", "dozen": "dozen", "dozens": "dozen", "dz": "dozen",
    "bag": "bags", "bags": "bags", "package": "packages", "packages": "packages",
}


class UnitError(Exception):
    """A pair of units that cannot be converted."""


def unit_key(unit: str) -> str | None:
    """The canonical unit for a spelling (case and spaces ignored); None if unknown."""
    return _UNIT_NAMES.get("".join(unit.split()).casefold())


def convert(qty: float, unit: str, food_unit: str) -> float:
    """qty given in `unit` (canonical) as a number of the food's unit. Raises UnitError."""
    if unit == food_unit:
        return qty
    if unit == "each" and food_unit == "dozen":
        return qty / PER_DOZEN
    if unit == "dozen" and food_unit == "each":
        return qty * PER_DOZEN
    raise UnitError(f'unit "{unit}" cannot be used for a food counted in {food_unit}')

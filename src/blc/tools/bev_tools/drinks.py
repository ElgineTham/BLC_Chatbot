"""Turning the user's drink requests into resolved drinks, amounts and BEO lines."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from blc.pull_sheet import EACH, GALLON, BeoLine, Catalog
from blc.pull_sheet.text import guests_to_gallons, norm

GALLON_UNITS: tuple[str, ...] = ("gallon", "gallons", "gal")
# Short names a user says that are not menu names (the only menu knowledge outside the JSON).
SHORT_NAMES: dict[str, str] = {"tea": "Hot water", "hot tea": "Hot water", "juice": "Orange juice"}


class BevInputError(Exception):
    """The request is wrong in a way the user can fix (becomes status "invalid")."""


@dataclass(frozen=True)
class DrinkRequest:
    menu: str                      # a drink or package name as the user said it
    quantity: float | None = None  # amount of this drink, if the user gave one
    unit: str | None = None        # "gallon"/"gallons"/"gal" or "each"; None = the item's own unit


@dataclass(frozen=True)
class DrinkAmount:
    drink: str          # menu display name, e.g. "Coffee"
    amount: Fraction    # gallons for gallon items, pieces for each items
    unit: str           # "gallon" or "each"
    from_guests: bool   # True if the amount was worked out from `guests`


@dataclass(frozen=True)
class Sized:
    """An amount (None = not known) and whether it came from the guest count."""

    amount: Fraction | None
    from_guests: bool


@dataclass(frozen=True)
class Plan:
    order: tuple[tuple[str, str], ...]   # ("item" | "package", display), first-seen order
    own: dict[str, Sized]                # amounts of the individually requested items
    not_on_menu: tuple[str, ...]


def _larger(first: Sized, second: Sized) -> Sized:
    if second.amount is None:
        return first
    if first.amount is None or second.amount > first.amount:
        return second
    return first


def _quantity(request: DrinkRequest) -> Fraction | None:
    value = request.quantity
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise BevInputError(f"quantity for {request.menu!r} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise BevInputError(f"quantity for {request.menu!r} must be a number")
    if value <= 0:
        raise BevInputError(f"quantity for {request.menu!r} must be more than 0")
    return Fraction(str(value))


def _unit_ok(request: DrinkRequest, item_unit: str) -> None:
    if request.unit is None:
        return
    unit = norm(request.unit) if isinstance(request.unit, str) else ""
    if unit in GALLON_UNITS and item_unit == GALLON:
        return
    if unit == EACH and item_unit == EACH:
        return
    raise BevInputError(
        f"unit {request.unit!r} does not fit {request.menu!r} "
        f"(it is counted in {'gallons' if item_unit == GALLON else 'each'})"
    )


def _own_amount(request: DrinkRequest, item_unit: str, guests: int | None) -> Sized:
    quantity = _quantity(request)
    if quantity is not None:
        _unit_ok(request, item_unit)
        return Sized(quantity, False)
    if item_unit == GALLON and guests is not None:
        return Sized(guests_to_gallons(guests), True)
    return Sized(None, False)


def resolve_requests(
    catalog: Catalog, requests: Sequence[DrinkRequest], guests: int | None
) -> Plan:
    """Match names to the menu and size each requested item. Raises BevInputError."""
    for request in requests:
        _quantity(request)
    order: list[tuple[str, str]] = []
    own: dict[str, Sized] = {}
    unknown: list[str] = []
    for request in requests:
        name = request.menu.strip()
        hit = catalog._names.get(norm(name))
        if hit is None and norm(name) in SHORT_NAMES:
            short = SHORT_NAMES[norm(name)]
            hit = ("item", short) if short in catalog._items else None
        if hit is None:
            unknown.append(name)
            continue
        kind, display = hit
        if kind == "package":
            if request.quantity is not None:
                raise BevInputError(
                    f"{display!r} is a package and a package is sized by guests, so pass "
                    "guests instead of gallons"
                )
            if (kind, display) not in order:
                order.append((kind, display))
            continue
        sized = _own_amount(request, catalog._items[display].unit, guests)
        if display in own:
            own[display] = _larger(own[display], sized)
        else:
            own[display] = sized
            order.append((kind, display))
    return Plan(tuple(order), own, tuple(unknown))


def expand_drinks(
    catalog: Catalog, plan: Plan, guests: int | None
) -> dict[str, Sized]:
    """Every resolved drink (packages expanded), in order, with the larger amount."""
    tagged = {tag for name in plan.own for tag in catalog._items[name].tags}
    result: dict[str, Sized] = {}

    def add(display: str, sized: Sized) -> None:
        result[display] = _larger(result[display], sized) if display in result else sized

    from_guests = (
        Sized(guests_to_gallons(guests), True) if guests is not None else Sized(None, False)
    )
    for kind, display in plan.order:
        if kind == "item":
            add(display, plan.own[display])
            continue
        package = catalog._packages[display]
        for name in package.includes:
            add(name, from_guests)
        for tag, default in package.placeholders:
            if tag not in tagged:
                add(default, from_guests)
    return result


def drink_amounts(catalog: Catalog, drinks: dict[str, Sized]) -> tuple[DrinkAmount, ...]:
    return tuple(
        DrinkAmount(name, sized.amount, catalog._items[name].unit, sized.from_guests)
        for name, sized in drinks.items()
        if sized.amount is not None
    )


def missing_gallon_amounts(catalog: Catalog, drinks: dict[str, Sized]) -> bool:
    return any(
        sized.amount is None and catalog._items[name].unit == GALLON
        for name, sized in drinks.items()
    )


def beo_lines(
    catalog: Catalog, plan: Plan, guests: int | None
) -> tuple[BeoLine, ...]:
    """BEO lines equivalent to the plan; unknown amounts get a nominal 1."""
    lines: list[BeoLine] = []
    for kind, display in plan.order:
        if kind == "package":
            lines.append(BeoLine(display, Fraction(guests or 1), ""))
            continue
        sized = plan.own[display]
        unit = catalog._items[display].unit
        if sized.from_guests and guests is not None:
            lines.append(BeoLine(display, Fraction(guests), ""))
        elif sized.amount is not None:
            lines.append(BeoLine(display, sized.amount, unit))
        else:
            lines.append(BeoLine(display, Fraction(1), unit))
    return tuple(lines)

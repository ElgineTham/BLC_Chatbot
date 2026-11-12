"""run_bev_tool: reads the raw argument dict the chat model sends (spec 005 section 4.0)."""

from __future__ import annotations

import math
from collections.abc import Mapping

from blc.pull_sheet import Catalog
from blc.tools.bev_tools.calculator import BevResult, calculate_bev_item, invalid_result
from blc.tools.bev_tools.drinks import BevInputError, DrinkRequest

NAME_KEYS: tuple[str, ...] = ("menu", "name", "menu_name", "drink")
AMOUNT_KEYS: tuple[str, ...] = ("quantity", "gallons", "amount")

# (name, amount, unit) as read from one entry of "drinks"
_Entry = tuple[str, "int | float | None", "str | None"]


def _number(value: object, name: str) -> int | float:
    """A finite number from a number or a numeric string; BevInputError otherwise."""
    if isinstance(value, bool):
        raise BevInputError(f"{name} must be a number")
    if isinstance(value, (int, float)):
        number: int | float = value
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            raise BevInputError(f"{name} must be a number, got {value!r}") from None
    else:
        raise BevInputError(f"{name} must be a number")
    if isinstance(number, float) and not math.isfinite(number):
        raise BevInputError(f"{name} must be a number")
    return number


def _amount(value: object, name: str) -> int | float | None:
    """None for null/0 (not given); BevInputError for a negative or non-number."""
    if value is None:
        return None
    number = _number(value, name)
    if number < 0:
        raise BevInputError(f"{name} must not be negative")
    return None if number == 0 else number


def _guests(value: object) -> int | None:
    if value is None:
        return None
    number = _number(value, "guests")
    if number == 0:
        return None
    if number < 0 or number != int(number):
        raise BevInputError("guests must be a whole number of 1 or more")
    return int(number)


def _first_key(raw: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    return next((key for key in keys if key in raw), None)


def _object_entry(raw: Mapping[str, object]) -> _Entry:
    name_key = _first_key(raw, NAME_KEYS)
    if name_key is None:
        raise BevInputError('each drink object needs a name under "menu" or "name"')
    name = raw[name_key]
    if not isinstance(name, str) or not name.strip():
        raise BevInputError("each drink needs a menu name")
    amount_key = _first_key(raw, AMOUNT_KEYS)
    amount = None if amount_key is None else _amount(raw[amount_key], "quantity")
    unit = raw.get("unit")
    if unit is not None and not isinstance(unit, str):
        raise BevInputError("unit must be text")
    return name, amount, unit


def _list_entry(raw: object) -> _Entry:
    if isinstance(raw, str):
        return raw, None, None
    if isinstance(raw, Mapping):
        return _object_entry(raw)
    raise BevInputError("each drink must be a name")


def _drink_entries(raw: object) -> tuple[list[_Entry], bool]:
    """The drinks as entries, and whether the entries carry their own amounts."""
    if raw is None:
        return [], False
    if isinstance(raw, str):
        return ([(raw, None, None)] if raw.strip() else []), False
    if isinstance(raw, Mapping):
        entries: list[_Entry] = [
            (str(name), _amount(value, "quantity"), None) for name, value in raw.items()
        ]
        return entries, any(entry[1] is not None for entry in entries)
    if isinstance(raw, (list, tuple)):
        entries = [_list_entry(item) for item in raw]
        return entries, any(entry[1] is not None for entry in entries)
    raise BevInputError("drinks must be a list of drink names")


def _gallons(raw: object) -> list[int | float | None]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [_amount(value, "gallons") for value in raw]
    return [_amount(raw, "gallons")]


def _requests(args: Mapping[str, object]) -> tuple[DrinkRequest, ...]:
    entries, own_amounts = _drink_entries(args.get("drinks"))
    gallons = _gallons(args.get("gallons"))
    if not gallons:
        return tuple(DrinkRequest(name, amount, unit) for name, amount, unit in entries)
    if own_amounts:
        raise BevInputError('amounts were given twice: in "drinks" and in "gallons"')
    if not entries:
        raise BevInputError('"gallons" needs "drinks"')
    if len(gallons) == 1:
        gallons = gallons * len(entries)
    if len(gallons) != len(entries):
        raise BevInputError('"gallons" must have one number per drink, in the same order')
    return tuple(
        DrinkRequest(name, amount, unit)
        for (name, _, unit), amount in zip(entries, gallons)
    )


def run_bev_tool(args: Mapping[str, object], catalog: Catalog | None = None) -> BevResult:
    """Run the tool on a raw argument dict; a bad argument gives status "invalid"."""
    try:
        if not isinstance(args, Mapping):
            raise BevInputError("arguments must be an object")
        item = args.get("item")
        if not isinstance(item, str):
            raise BevInputError("item is required")
        drinks = _requests(args)
        guests = _guests(args.get("guests"))
    except BevInputError as error:
        return invalid_result(str(error))
    return calculate_bev_item(item, drinks, guests, catalog)

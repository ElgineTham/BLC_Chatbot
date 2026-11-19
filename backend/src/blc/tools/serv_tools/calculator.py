"""Totalling serving utensils for the food lines of an order (spec 042 4.1-4.3); no I/O."""

from __future__ import annotations

import math

from blc.tools.serv_tools.reply_text import invalid_text, need_info_text, ok_text
from blc.tools.serv_tools.result import SERV_UTENSILS, ServResult
from blc.tools.serv_tools.rules import FoodRule, ServRules, load_serv_rules
from blc.tools.serv_tools.units import UnitError, convert, unit_key

_ROUNDING = 9


class _Problem(Exception):
    """A value that makes the call invalid; the message says what was wrong."""


def _check_qty(value: object) -> float | None:
    """A number above 0; None when not given (missing, null, 0, blank)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise _Problem(f"qty {value!r} is not a number")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise _Problem(f"qty {value!r} is not a number") from None
    if math.isnan(number) or math.isinf(number):
        raise _Problem(f"qty {value!r} is not a number")
    if number < 0:
        raise _Problem(f"qty {value!r} is negative")
    return number or None


def _check_unit(value: object) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    key = unit_key(value) if isinstance(value, str) else None
    if key is None:
        raise _Problem(f"unit {value!r} is not a known unit (each, dozen, bags, packages)")
    return key


def _find_food(value: object, rules: ServRules) -> FoodRule:
    rule = rules.find(value) if isinstance(value, str) else None
    if rule is None:
        raise _Problem(f"unknown food {value!r}; it is not a food on the menu")
    return rule


def _line_totals(rule: FoodRule, qty: float, unit: str | None) -> dict[str, int]:
    try:
        amount = convert(qty, unit or rule.unit, rule.unit)
    except UnitError as error:
        raise _Problem(f"{rule.name}: {error}") from None
    totals: dict[str, int] = {}
    for entry in rule.utensils:
        times = 1 if entry.per is None else math.ceil(round(amount / entry.per, _ROUNDING))
        totals[entry.utensil] = totals.get(entry.utensil, 0) + entry.count * times
    return totals


def calculate_serving_utensils(
    lines: list[tuple[str, float | None, str | None]],
    rules: ServRules | None = None,
) -> ServResult:
    """Each line is (food, qty, unit). Never raises for bad user input."""
    rules = rules if rules is not None else load_serv_rules()
    problems: list[str] = []
    unknown_food = False
    missing: list[str] = []
    foods: list[str] = []
    readings: list[tuple[str, float, str]] = []
    totals: dict[str, int] = {}
    for food, qty, unit in lines:
        try:
            try:
                rule = _find_food(food, rules)
            except _Problem:
                unknown_food = True
                raise
            number, given_unit = _check_qty(qty), _check_unit(unit)
            if number is None:
                missing.append(rule.name)
                foods.append(rule.name)
                continue
            line = _line_totals(rule, number, given_unit)
        except _Problem as problem:
            problems.append(str(problem))
            continue
        foods.append(rule.name)
        readings.append((rule.name, number, given_unit or rule.unit))
        for name, total in line.items():
            totals[name] = totals.get(name, 0) + total
    if problems:
        return ServResult("invalid", invalid_text(problems, unknown_food), None, None)
    if missing:
        return ServResult("need_info", need_info_text(list(dict.fromkeys(missing))), None, None)
    utensils = {name: totals[name] for name in SERV_UTENSILS if totals.get(name, 0) > 0}
    return ServResult("ok", ok_text(utensils, readings), utensils, tuple(foods))

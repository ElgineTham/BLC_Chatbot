"""The food calculation: counts and napkin answers (spec 029 4.2 to 4.5). No I/O here
except loading the real rules when none are given."""

from __future__ import annotations

from blc.tools.food_tools.checks import BadValue, check_guests, check_item, check_meal
from blc.tools.food_tools.reply_text import (
    invalid_text,
    need_info_text,
    ok_count_text,
    ok_napkin_text,
)
from blc.tools.food_tools.result import COUNT_ITEMS, FoodResult
from blc.tools.food_tools.rules import FoodRules, load_food_rules


def _count_result(item: str, guests: int, rules: FoodRules) -> FoodResult:
    extra = rules.extra_for(guests)
    count = guests + extra
    text = ok_count_text(item, guests, extra, count)
    return FoodResult("ok", text, item=item, guests=guests, extra=extra, count=count)


def _napkin_result(item: str, meal: str, rules: FoodRules) -> FoodResult:
    answer = bool(rules.napkin(meal, item.split()[0]))
    return FoodResult("ok", ok_napkin_text(item, meal, answer), item=item, answer=answer, meal=meal)


def calculate_food_item(
    item: str,
    guests: int | None = None,
    meal: str | None = None,
    rules: FoodRules | None = None,
) -> FoodResult:
    """Pure calculation. Never raises for bad user input; FoodRulesError propagates."""
    rules = rules if rules is not None else load_food_rules()
    try:
        name = check_item(item)
    except BadValue as error:
        return FoodResult("invalid", invalid_text(str(error), show_items=True))
    try:
        if name in COUNT_ITEMS:
            number = check_guests(guests)
            if number is not None:
                return _count_result(name, number, rules)
        else:
            canonical = check_meal(meal, rules.meals())
            if canonical is not None:
                return _napkin_result(name, canonical, rules)
    except BadValue as error:
        return FoodResult("invalid", invalid_text(str(error), show_items=False), item=name)
    return FoodResult("need_info", need_info_text(name, rules.meals()), item=name)

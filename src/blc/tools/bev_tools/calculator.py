"""calculate_bev_item: answers pull sheet number questions with the pull sheet code."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from blc.pull_sheet import (
    EACH,
    Beo,
    Catalog,
    PullLine,
    build_pull_sheet,
    load_catalog,
)
from blc.pull_sheet.supplies import _extra_for
from blc.pull_sheet.text import guests_to_gallons, norm
from blc.tools.bev_tools.drinks import (
    BevInputError,
    DrinkAmount,
    DrinkRequest,
    Plan,
    Sized,
    beo_lines,
    drink_amounts,
    expand_drinks,
    missing_gallon_amounts,
    resolve_requests,
)
from blc.tools.bev_tools.reply_text import (
    invalid_text,
    need_info_question,
    not_on_menu_text,
    ok_text,
)

BEV_ITEMS: tuple[str, ...] = ("gallons", "cambros", "cups", "supplies", "everything")
BEV_STATUSES: tuple[str, ...] = ("ok", "need_info", "not_on_menu", "invalid")
CUP_RULE = "guest+extra"
GUEST_RULES: tuple[str, ...] = ("guest", "guest+extra")


@dataclass(frozen=True)
class BevResult:
    status: str                       # one of BEV_STATUSES
    text: str                         # what the tool returns to the chat model
    drinks: tuple[DrinkAmount, ...]   # resolved drinks with the amounts used; () unless "ok"
    lines: tuple[PullLine, ...]       # pull lines answering the item; () unless "ok"
    not_on_menu: tuple[str, ...]      # requested names not on the menu, in request order
    gallons_each: int | None          # item "gallons" with no drinks: gallons per drink
    cups_each: int | None             # item "cups" with no drinks: cups (guests + extras)


def _result(
    status: str,
    text: str,
    not_on_menu: tuple[str, ...] = (),
    drinks: tuple[DrinkAmount, ...] = (),
    lines: tuple[PullLine, ...] = (),
    gallons_each: int | None = None,
    cups_each: int | None = None,
) -> BevResult:
    if not_on_menu and status != "not_on_menu":
        text = f"{text}\n{not_on_menu_text(not_on_menu)}"
    return BevResult(status, text, drinks, lines, not_on_menu, gallons_each, cups_each)


def invalid_result(reason: str) -> BevResult:
    return _result("invalid", invalid_text(reason))


def _check_basics(item: object, guests: object) -> None:
    if not isinstance(item, str) or item not in BEV_ITEMS:
        raise BevInputError(f"item must be one of {', '.join(BEV_ITEMS)}")
    if guests is not None and (
        isinstance(guests, bool) or not isinstance(guests, int) or guests < 1
    ):
        raise BevInputError("guests must be a whole number of 1 or more")


def _missing(
    item: str, no_drinks: bool, guests: int | None, gallons_missing: bool
) -> list[str]:
    if item == "gallons" and no_drinks:
        return ["anything"] if guests is None else []
    missing: list[str] = []
    if no_drinks and item not in ("gallons", "cups"):
        missing.append("drink")
    if item == "cups" and guests is None:
        missing.append("guests")
    if item in ("gallons", "cambros", "everything") and gallons_missing and not no_drinks:
        missing.append("gallons")
    return missing


def _name_sets(catalog: Catalog) -> tuple[set[str], set[str], set[str]]:
    cambros = {c.name for c in catalog._cambros}
    adds = {i.display for i in catalog._items.values() if i.unit == EACH}
    guest_names = {norm(s.name) for s in catalog._supplies if s.per in GUEST_RULES}
    return cambros, adds, guest_names


def _select(
    catalog: Catalog,
    item: str,
    lines: tuple[PullLine, ...],
    guests: int | None,
    sized_names: set[str],
) -> tuple[tuple[PullLine, ...], bool]:
    cambros, adds, guest_names = _name_sets(catalog)
    cup_names = {norm(s.name) for s in catalog._supplies if s.per == CUP_RULE}
    cambro_part = [ln for ln in lines if ln.supply in cambros]
    add_part = [ln for ln in lines if ln.supply in adds and ln.supply in sized_names]
    supply_part = [ln for ln in lines if ln.supply not in cambros | adds]
    left_out = False
    if guests is None:
        kept = [ln for ln in supply_part if norm(ln.supply) not in guest_names]
        left_out = len(kept) != len(supply_part)
        supply_part = kept
    if item == "cambros":
        return tuple(cambro_part), False
    if item == "cups":
        return tuple(ln for ln in supply_part if norm(ln.supply) in cup_names), False
    if item == "supplies":
        return tuple(supply_part), left_out
    return tuple(cambro_part + add_part + supply_part), left_out


def _answer(
    catalog: Catalog,
    item: str,
    plan: Plan,
    drinks: dict[str, Sized],
    guests: int | None,
) -> BevResult:
    amounts = drink_amounts(catalog, drinks)
    names = tuple(drinks)
    if item == "gallons":
        each = guests_to_gallons(guests) if not plan.order and guests else None
        gallons_each = int(each) if each is not None else None
        text = ok_text(amounts, (), guests, gallons_each, False)
        return _result("ok", text, plan.not_on_menu, amounts, (), gallons_each)
    if item == "cups" and not plan.order:
        cups_each = guests + _extra_for(catalog, guests)
        text = ok_text(amounts, (), guests, None, False, cups_each=cups_each)
        return _result("ok", text, plan.not_on_menu, amounts, (), None, cups_each)
    sheet = build_pull_sheet(catalog, Beo(guests or 1, beo_lines(catalog, plan, guests)))
    sized = {name for name, sized_ in drinks.items() if sized_.amount is not None}
    lines, left_out = _select(catalog, item, sheet.lines, guests, sized)
    text = ok_text(amounts, lines, guests, None, left_out, names)
    return _result("ok", text, plan.not_on_menu, amounts, lines, None)


def calculate_bev_item(
    item: str,
    drinks: Sequence[DrinkRequest] = (),
    guests: int | None = None,
    catalog: Catalog | None = None,
) -> BevResult:
    """Pure calculation, no I/O except loading the catalog (see spec 005 section 4)."""
    if catalog is None:
        catalog = load_catalog()
    try:
        _check_basics(item, guests)
        plan = resolve_requests(catalog, drinks, guests)
    except BevInputError as error:
        return invalid_result(str(error))
    if drinks and not plan.order:
        return _result("not_on_menu", not_on_menu_text(plan.not_on_menu), plan.not_on_menu)
    resolved = expand_drinks(catalog, plan, guests)
    gallons_missing = missing_gallon_amounts(catalog, resolved)
    missing = _missing(item, not drinks, guests, gallons_missing)
    if missing:
        return _result("need_info", need_info_question(missing), plan.not_on_menu)
    return _answer(catalog, item, plan, resolved, guests)

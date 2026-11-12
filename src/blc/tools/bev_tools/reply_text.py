"""The short plain-English text the tool returns to the chat model (no I/O)."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from blc.pull_sheet import EACH, PullLine
from blc.tools.bev_tools.drinks import DrinkAmount

NOT_ON_MENU_PHRASE = "not on the beverage menu"
GUEST_NOTE = "Cup counts need the number of guests."
ASK_GALLONS_OR_GUESTS = "How many gallons of each drink, or how many guests?"
ASK_ANYTHING = "Which drinks and how many gallons of each, or how many guests?"
ASK_DRINK = "Which drink"
ASK_GUESTS = "how many guests"
_CAMBRO_MARK = "cambros["


def format_number(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):g}"


def not_on_menu_text(names: Sequence[str]) -> str:
    return " ".join(f"{name} is {NOT_ON_MENU_PHRASE}." for name in names)


INVALID_FORMAT = (
    'Expected arguments: {"item": one of gallons, cambros, cups, supplies, everything; '
    '"drinks": list of drink names (optional); "gallons": list of numbers in the same '
    'order as "drinks" (optional); "guests": whole number (optional)}. '
    'Example: {"item": "cambros", "drinks": ["brewed hot cider", "peach tea"], '
    '"gallons": [6, 4], "guests": 45}'
)


def count_word(count: int, singular: str) -> str:
    """"1 guest", "2 guests"."""
    return f"{count} {singular}" if count == 1 else f"{count} {singular}s"


def invalid_text(reason: str) -> str:
    return f"invalid request: {reason}. {INVALID_FORMAT}"


def need_info_question(missing: Sequence[str]) -> str:
    """missing holds "drink", "guests", "gallons" or "anything"."""
    if "anything" in missing:
        return ASK_ANYTHING
    if "gallons" in missing and "drink" not in missing:
        return ASK_GALLONS_OR_GUESTS
    parts: list[str] = []
    if "drink" in missing:
        parts.append(ASK_DRINK)
    if "guests" in missing:
        parts.append(ASK_GUESTS)
    if "gallons" in missing:
        parts.append("how many gallons of each drink")
    sentence = ", and ".join(parts)
    return sentence[0].upper() + sentence[1:] + "?"


def _drink_sentence(amount: DrinkAmount, guests: int | None) -> str:
    suffix = "each" if amount.unit == EACH else "gal"
    text = f"{amount.drink}: {format_number(amount.amount)} {suffix}"
    if amount.from_guests:
        text += f" from {count_word(guests, 'guest')}"
    return text + "."


def _cambro_note(line: PullLine) -> str:
    drinks = [r.split(": ", 1)[1] for r in line.reasons if _CAMBRO_MARK in r and ": " in r]
    if not drinks:
        return ""
    if line.quantity == len(drinks):
        return " (" + ", ".join(f"one for {d}" for d in drinks) + ")"
    return " (for " + ", ".join(drinks) + ")"


def _line_sentence(line: PullLine) -> str:
    quantity = "bring" if line.quantity is None else str(line.quantity)
    return f"{line.supply}: {quantity}{_cambro_note(line)}."


def ok_text(
    drinks: Sequence[DrinkAmount],
    lines: Sequence[PullLine],
    guests: int | None,
    gallons_each: int | None,
    guest_note: bool,
    drink_names: Sequence[str] = (),
    cups_each: int | None = None,
) -> str:
    rows: list[str] = []
    if drinks:
        rows.append(" ".join(_drink_sentence(d, guests) for d in drinks))
    elif drink_names:
        rows.append("Drinks: " + ", ".join(drink_names) + ".")
    if gallons_each is not None:
        rows.append(
            f"For {count_word(guests, 'guest')}: "
            f"{count_word(gallons_each, 'gallon')} of each drink."
        )
    if cups_each is not None:
        rows.append(
            f"For {count_word(guests, 'guest')}: {count_word(cups_each, 'cup')} "
            "(guests plus extras). The same count applies to hot cups and to cold cups."
        )
    rows.extend(_line_sentence(line) for line in lines)
    if guest_note:
        rows.append(GUEST_NOTE)
    return "\n".join(rows)



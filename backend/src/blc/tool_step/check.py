"""Refuses tool arguments that do not agree with the question (spec 009). No I/O."""

from __future__ import annotations

import re
from collections.abc import Mapping

from blc.router.items import pull_sheet_items_in
from blc.tool_step.numbers import ALWAYS_ACCEPTED, as_number, numbers_in

REJECTED_PREFIX = "invalid (check): "
NUMBER_ARGUMENTS: tuple[str, ...] = ("guests", "gallons")
EVERYTHING = "everything"
BEV_TOOL = "calculate_bev_item"
RECIPE_TOOL = "scale_recipe"
NUMBER_REASON = (
    "{prefix}{argument} {shown} is not in the question; use only amounts the user gave "
    "and leave {argument} out when the user gave none."
)
EVERYTHING_REASON = (
    "{prefix}the question asks what to bring in general, so item must be everything."
)


def _values(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _unsupported_number(args: Mapping[str, object], question: str) -> str | None:
    present = numbers_in(question)
    for argument in NUMBER_ARGUMENTS:
        for value in _values(args.get(argument)):
            number = as_number(value)
            if number is None or number == ALWAYS_ACCEPTED or number in present:
                continue
            return NUMBER_REASON.format(
                prefix=REJECTED_PREFIX, argument=argument, shown=_one_line(str(value))
            )
    return None


def _wrong_item(args: Mapping[str, object], question: str) -> str | None:
    if pull_sheet_items_in(question) != (EVERYTHING,):
        return None
    item = args.get("item")
    if isinstance(item, str) and item.strip().casefold() == EVERYTHING:
        return None
    return EVERYTHING_REASON.format(prefix=REJECTED_PREFIX)


def check_arguments(
    args: Mapping[str, object], question: str, tool: str = BEV_TOOL
) -> str | None:
    """None if the arguments agree with the question, else one sentence starting with
    REJECTED_PREFIX saying what to change. For tool="scale_recipe" only the number rule
    applies. Never raises."""
    try:
        if tool == RECIPE_TOOL:
            return _unsupported_number(args, question)
        return _unsupported_number(args, question) or _wrong_item(args, question)
    except Exception:  # the check must never break the chat
        return None

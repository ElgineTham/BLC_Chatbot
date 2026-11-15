"""Finding numbers in a planned call that the user never gave (spec 021 section 4.1 to 4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from blc.tool_step.numbers import ALWAYS_ACCEPTED, as_number, numbers_in
from blc.tools.bev_tools import BEV_TOOL_NAME
from blc.tools.recipe_tools import RECIPE_TOOL_NAME

CHECKED_ARGUMENTS: tuple[str, ...] = ("guests", "gallons")
CHECKED_TOOLS: frozenset[str] = frozenset({BEV_TOOL_NAME, RECIPE_TOOL_NAME})


@dataclass(frozen=True)
class RejectedCall:
    name: str
    args: dict[str, object]
    invented: dict[str, tuple[object, ...]]


def allowed_numbers(question: str, history: list[dict[str, str]] | None = None) -> set[float]:
    """Every number in the question and in the content of every history item; 1 always."""
    texts = [question.strip() if isinstance(question, str) else ""]
    for item in history or []:
        content = item.get("content") if isinstance(item, Mapping) else None
        if isinstance(content, str):
            texts.append(content)
    allowed = {ALWAYS_ACCEPTED}
    for text in texts:
        allowed |= numbers_in(text)
    return allowed


def _values_of(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def invented_numbers(
    name: str,
    args: Mapping[str, object],
    question: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, tuple[object, ...]]:
    """Each checked argument with invented values, mapped to those values. Never raises."""
    try:
        if name not in CHECKED_TOOLS:
            return {}
        allowed = allowed_numbers(question, history)
        found: dict[str, tuple[object, ...]] = {}
        for key in CHECKED_ARGUMENTS:
            bad = tuple(
                value for value in _values_of(args.get(key))
                if (number := as_number(value)) is not None and number not in allowed
            )
            if bad:
                found[key] = bad
        return found
    except Exception:  # noqa: BLE001 - the check must never raise
        return {}

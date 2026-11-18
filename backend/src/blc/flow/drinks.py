"""Fill in the drink a user named when the planner left it out (spec 022 section 4)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from blc.planner import Plan, PlannedCall
from blc.tools.bev_tools import BEV_TOOL_NAME

FROM_QUESTION = "question"
FROM_HISTORY = "history"
DRINKS_ARGUMENT = "drinks"
USER_ROLE = "user"


@dataclass(frozen=True)
class FilledDrinks:
    call_index: int
    drinks: tuple[str, ...]
    source: str


def _normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def drinks_named(text: str, names: Mapping[str, str]) -> tuple[str, ...]:
    """Display names of the menu drinks named in text, by first appearance, no repeats."""
    try:
        haystack = _normalise(text)
        spans: list[tuple[int, int, str]] = []
        for name in sorted((n for n in names if n), key=len, reverse=True):
            pattern = r"(?<![^\W\d_])" + re.escape(name) + r"(?![^\W\d_])"
            for match in re.finditer(pattern, haystack):
                start, end = match.span()
                if not any(start < e and s < end for s, e, _ in spans):
                    spans.append((start, end, names[name]))
        result: list[str] = []
        for _s, _e, display in sorted(spans):
            if display not in result:
                result.append(display)
        return tuple(result)
    except Exception:  # noqa: BLE001 - must never raise
        return ()


def _has_no_drinks(args: Mapping[str, object]) -> bool:
    value = args.get(DRINKS_ARGUMENT)
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def _find_source(
    question: str, history: list[dict[str, str]] | None, names: Mapping[str, str]
) -> tuple[tuple[str, ...], str]:
    named = drinks_named(question, names)
    if named:
        return named, FROM_QUESTION
    for item in reversed(history or []):
        if not isinstance(item, Mapping) or item.get("role") != USER_ROLE:
            continue
        content = item.get("content")
        named = drinks_named(content, names) if isinstance(content, str) else ()
        if named:
            return named, FROM_HISTORY
    return (), FROM_HISTORY


def fill_missing_drinks(
    plan: Plan,
    question: str,
    history: list[dict[str, str]] | None,
    names: Mapping[str, str],
) -> tuple[Plan, FilledDrinks | None]:
    """The plan with its one drink-less calculate_bev_item call given the named drinks."""
    try:
        bev = [i for i, call in enumerate(plan.calls) if call.name == BEV_TOOL_NAME]
        if len(bev) != 1 or not _has_no_drinks(plan.calls[bev[0]].args):
            return plan, None
        named, source = _find_source(question, history, names)
        if not named:
            return plan, None
        index = bev[0]
        call = plan.calls[index]
        filled = PlannedCall(call.name, {**call.args, DRINKS_ARGUMENT: list(named)})
        calls = plan.calls[:index] + (filled,) + plan.calls[index + 1:]
        return Plan(plan.route, calls, plan.fallback), FilledDrinks(index, named, source)
    except Exception:  # noqa: BLE001 - must never raise
        return plan, None

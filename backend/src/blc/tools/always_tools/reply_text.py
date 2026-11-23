"""Text the Always items tool returns to the chat model (spec 044)."""

from __future__ import annotations

from blc.tools.always_tools.result import ALWAYS_COUNT_ITEMS

FIELD_LABELS: dict[str, str] = {"tables": "tables", "drip_trays": "drip trays"}
EXAMPLE_CALL = '{"tables": 2, "drip_trays": 3}'


def ok_text(counts: dict[str, int]) -> str:
    lines = ["Bus tubs: check", "Towels: check"]
    lines += [f"{item.capitalize()}: {counts[item]}" for item in ALWAYS_COUNT_ITEMS]
    return "\n".join(lines)


def need_info_text(missing: list[str]) -> str:
    labels = " and ".join(FIELD_LABELS[name] for name in missing)
    return f"Please tell me how many {labels} there are?"


def invalid_text(bad: list[str]) -> str:
    fields = ", ".join(bad) if bad else "arguments"
    return (
        f"invalid {fields}: each value must be a whole number of 0 or more. "
        f"Expected format, for example: {EXAMPLE_CALL}"
    )

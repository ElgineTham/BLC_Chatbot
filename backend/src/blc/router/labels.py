"""Labelling parts: the no-model shortcut and reading the model's letters (spec 013 4.3, 4.5)."""

from __future__ import annotations

import re

from blc.router.items import pull_sheet_items_in
from blc.tool_step.numbers import numbers_in

_TOKEN_SPLIT = re.compile(r"[^A-Za-z]+")
_LETTERS = re.compile(r"[td]+", re.IGNORECASE)


def quick_label(text: str) -> str | None:
    """"DOCS" if the text has no number and no pull sheet word, else None."""
    if not isinstance(text, str) or not text.strip():
        return "DOCS"
    if numbers_in(text) or pull_sheet_items_in(text):
        return None
    return "DOCS"


def read_labels(reply: str, count: int) -> tuple[str, ...] | None:
    """One "TOOL"/"DOCS" label per part from the model's reply, or None if the reply is
    unreadable or has fewer than count labels."""
    labels: list[str] = []
    for token in _TOKEN_SPLIT.split(reply):
        if len(labels) >= count:
            break
        if not token:
            continue
        lower = token.lower()
        if _LETTERS.fullmatch(token):
            labels.extend("TOOL" if letter == "t" else "DOCS" for letter in lower)
        elif lower.startswith("tool"):
            labels.append("TOOL")
        elif lower.startswith("doc"):
            labels.append("DOCS")
        else:
            return None
    return tuple(labels[:count]) if len(labels) >= count else None

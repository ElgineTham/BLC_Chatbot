"""Recipe name matching: how a requested name is compared with the book's names (spec 015 4.2)."""

from __future__ import annotations

import re

_LEADING_THE = re.compile(r"^the\s+")
_TRAILING_RECIPE = re.compile(r"\s+recipe$")


def name_key(name: str) -> str:
    """Case, spaces, a leading "the" and a trailing word "recipe" do not matter."""
    key = " ".join(name.casefold().split())
    key = _LEADING_THE.sub("", key)
    return _TRAILING_RECIPE.sub("", key)

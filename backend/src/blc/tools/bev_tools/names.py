"""Name normalisation for menu and supply names."""

from __future__ import annotations


def norm(text: str) -> str:
    return " ".join(text.casefold().split())

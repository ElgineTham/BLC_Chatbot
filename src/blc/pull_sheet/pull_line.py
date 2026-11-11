"""The PullLine result record."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PullLine:
    supply: str
    quantity: int | None
    reasons: tuple[str, ...]

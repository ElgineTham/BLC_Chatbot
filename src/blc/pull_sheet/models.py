"""Validated catalog entries (internal)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class Item:
    display: str
    unit: str
    tags: frozenset[str]


@dataclass(frozen=True)
class Package:
    display: str
    includes: tuple[str, ...]  # item display names
    placeholders: tuple[tuple[str, str], ...]  # (tag, default item display)


@dataclass(frozen=True)
class Cambro:
    index: int
    name: str
    gallons: Fraction


@dataclass(frozen=True)
class Supply:
    index: int
    name: str
    qty: Fraction | None
    per: str | None
    tick: bool
    tag: str | None

"""Counted-bag ingredients: file format (spec 040 4.1) and choosing bags (4.2). Pure calculation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

BAG_UNIT = "bag"


class BagFormatError(ValueError):
    """A counted-bag ingredient is malformed; book.py turns this into RecipeFileError."""


@dataclass(frozen=True)
class BagSize:
    name: str
    brews_from: int
    brews_to: int


def _whole(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BagFormatError(f"{what} must be a whole number of 1 or more")
    return value


def _size(raw: object, recipe: str) -> BagSize:
    if not isinstance(raw, dict):
        raise BagFormatError(f"{recipe}: a bag size must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise BagFormatError(f"{recipe}: a bag size needs a name")
    low = _whole(raw.get("brews_from"), f"{recipe}: {name} brews_from")
    high = _whole(raw.get("brews_to"), f"{recipe}: {name} brews_to")
    if low > high:
        raise BagFormatError(f"{recipe}: {name} brews_from is above brews_to")
    return BagSize(name, low, high)


def parse_bags(raw: object, recipe: str) -> tuple[BagSize, ...]:
    """Raises BagFormatError."""
    if not isinstance(raw, list) or not raw:
        raise BagFormatError(f"{recipe}: bags must be a non-empty list")
    sizes = tuple(_size(item, recipe) for item in raw)
    if len({size.name for size in sizes}) != len(sizes):
        raise BagFormatError(f"{recipe}: two bag sizes share a name")
    if not any(size.brews_from == size.brews_to == 1 for size in sizes):
        raise BagFormatError(f"{recipe}: one bag size must brew exactly 1 gallon")
    return sizes


def _fits(sizes: tuple[BagSize, ...], counts: tuple[int, ...], gallons: int) -> bool:
    low = sum(s.brews_from * c for s, c in zip(sizes, counts))
    high = sum(s.brews_to * c for s, c in zip(sizes, counts))
    return low <= gallons <= high


def _splits(parts: int, total: int):
    """All ways to give `total` bags to `parts` sizes, fewest in the first sizes first."""
    if parts == 1:
        yield (total,)
        return
    for first in range(total + 1):
        for tail in _splits(parts - 1, total - first):
            yield (first, *tail)


def choose_bags(sizes: tuple[BagSize, ...], batch: Fraction) -> tuple[int, ...]:
    """Bag count per size (in the order of `sizes`) for the batch rounded up to whole gallons.

    Fewest bags in total; on a tie, fewest of the size with the smallest brews_to, then the next."""
    gallons = max(1, math.ceil(batch))
    order = sorted(range(len(sizes)), key=lambda i: sizes[i].brews_to)
    ranked = tuple(sizes[i] for i in order)
    for total in range(1, gallons + 1):
        for counts in _splits(len(ranked), total):
            if _fits(ranked, counts, gallons):
                result = [0] * len(sizes)
                for position, index in enumerate(order):
                    result[index] = counts[position]
                return tuple(result)
    raise BagFormatError("no bag count fits the batch")  # unreachable: a 1-gallon size exists

"""Name normalisation, number parsing and guests-to-gallons rounding."""

from __future__ import annotations

import math
import re
from fractions import Fraction

from blc.pull_sheet.constants import GUESTS_PER_GALLON
from blc.pull_sheet.errors import BeoError

_DECIMAL_RE = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", re.ASCII)
_FRACTION_RE = re.compile(r"([0-9]+)/([0-9]+)", re.ASCII)


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def parse_qty(text: str, lineno: int) -> Fraction:
    if _DECIMAL_RE.fullmatch(text):
        return Fraction(text)
    match = _FRACTION_RE.fullmatch(text)
    if match and int(match.group(2)) != 0:
        return Fraction(int(match.group(1)), int(match.group(2)))
    raise BeoError(f"invalid Qty {text!r}", lineno)


def guests_to_gallons(guests: Fraction | int) -> Fraction:
    """max(1, round_half_up(guests / 25)), exact."""
    raw = Fraction(guests) / GUESTS_PER_GALLON
    return Fraction(max(1, math.floor(raw + Fraction(1, 2))))

"""Guests-to-gallons rounding."""

from __future__ import annotations

import math
from fractions import Fraction

GUESTS_PER_GALLON = 25


def guests_to_gallons(guests: Fraction | int) -> Fraction:
    """max(1, round_half_up(guests / 25)), exact."""
    raw = Fraction(guests) / GUESTS_PER_GALLON
    return Fraction(max(1, math.floor(raw + Fraction(1, 2))))

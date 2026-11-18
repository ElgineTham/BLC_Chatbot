"""Plain-text rendering (spec 002 section 4.6)."""

from __future__ import annotations

from fractions import Fraction

from blc.pull_sheet.constants import TICK
from blc.pull_sheet.sheet import PullSheet


def _format_qty(qty: Fraction) -> str:
    if qty.denominator == 1:
        return str(qty.numerator)
    den = qty.denominator
    digits = 0
    power = 1
    while power % den != 0:
        power *= 10
        digits += 1
        if digits > 64:
            return f"{qty.numerator}/{qty.denominator}"
    scaled = qty.numerator * (power // den)
    text = str(scaled).rjust(digits + 1, "0")
    return f"{text[:-digits]}.{text[-digits:]}"


def format_pull_sheet(sheet: PullSheet) -> str:
    """Plain-text rendering, exact format in spec section 4.6."""
    out = [f"Pull sheet for {sheet.guests} guests", "", "Beverages"]
    if sheet.lines:
        for line in sheet.lines:
            shown = TICK if line.quantity is None else str(line.quantity)
            out.append(f"- {line.supply}: {shown}")
    else:
        out.append("- (none)")
    if sheet.skipped:
        out.extend(["", "Not used (check by hand):"])
        for skip in sheet.skipped:
            beo = skip.line
            amount = _format_qty(beo.qty)
            unit = f" {beo.unit}" if beo.unit else ""
            out.append(f"- {beo.name}, {amount}{unit}: {skip.problem}")
    return "\n".join(out) + "\n"

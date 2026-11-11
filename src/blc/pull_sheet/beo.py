"""BEO markdown parsing (spec 002 section 4.4)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from blc.pull_sheet.errors import BeoError
from blc.pull_sheet.text import parse_qty

_GUEST_RE = re.compile(r"^\s*guest\s+count\s*:(.*)$", re.IGNORECASE)
_INT_RE = re.compile(r"[0-9]+", re.ASCII)
_BEO_COLUMNS = frozenset({"description", "qty", "delivery uom"})


@dataclass(frozen=True)
class BeoLine:
    name: str
    qty: Fraction
    unit: str


@dataclass(frozen=True)
class Beo:
    guests: int
    lines: tuple[BeoLine, ...]


def _split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def _find_guests(rows: list[str]) -> int:
    found: list[tuple[int, str]] = []
    for number, raw in enumerate(rows, start=1):
        if raw.lstrip().startswith("|"):
            continue
        match = _GUEST_RE.match(raw)
        if match:
            found.append((number, match.group(1).strip()))
    if not found:
        raise BeoError("missing 'Guest Count' line")
    if len(found) > 1:
        raise BeoError("more than one 'Guest Count' line", found[1][0])
    number, value = found[0]
    if not _INT_RE.fullmatch(value) or int(value) < 1:
        raise BeoError(f"invalid Guest Count {value!r}", number)
    return int(value)


def _find_tables(rows: list[str]) -> list[list[tuple[int, str]]]:
    tables: list[list[tuple[int, str]]] = []
    previous = False
    for number, raw in enumerate(rows, start=1):
        is_row = raw.lstrip().startswith("|")
        if is_row:
            if not previous:
                tables.append([])
            tables[-1].append((number, raw))
        previous = is_row
    return tables


def _read_header(table: list[tuple[int, str]]) -> list[str]:
    head_no, head_raw = table[0]
    header = [c.strip().casefold() for c in _split_row(head_raw)]
    if len(header) != len(_BEO_COLUMNS) or set(header) != _BEO_COLUMNS:
        raise BeoError(
            "table header must be exactly Description | Qty | Delivery UOM", head_no
        )
    if len(table) < 2:
        raise BeoError("table has no separator row", head_no)
    sep_no, sep_raw = table[1]
    sep = _split_row(sep_raw)
    if len(sep) != len(header) or not all(
        cell and set(cell) <= set("-: ") for cell in sep
    ):
        raise BeoError("second table row must be a separator row", sep_no)
    return header


def _read_lines(table: list[tuple[int, str]], header: list[str]) -> tuple[BeoLine, ...]:
    col = {name: header.index(name) for name in _BEO_COLUMNS}
    lines: list[BeoLine] = []
    for number, raw in table[2:]:
        cells = _split_row(raw)
        if len(cells) != len(header):
            raise BeoError("row has the wrong number of cells", number)
        qty = parse_qty(cells[col["qty"]], number)
        if qty == 0:
            continue
        name = cells[col["description"]]
        if not name:
            raise BeoError("empty Description", number)
        lines.append(BeoLine(name, qty, cells[col["delivery uom"]]))
    return tuple(lines)


def parse_beo(text: str) -> Beo:
    """Parse the BEO markdown format of spec section 4.4."""
    rows = re.split(r"\r\n|\r|\n", text)
    guests = _find_guests(rows)
    tables = _find_tables(rows)
    if len(tables) > 1:
        raise BeoError("more than one table", tables[1][0][0])
    if not tables:
        return Beo(guests, ())
    header = _read_header(tables[0])
    return Beo(guests, _read_lines(tables[0], header))

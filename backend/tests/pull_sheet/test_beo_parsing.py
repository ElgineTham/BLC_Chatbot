"""parse_beo and BeoError.line (spec 002 §4.1, §4.4, EC-13, EC-27, EC-34). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
from fractions import Fraction

import pytest

from pull_sheet import BeoError, BeoLine, parse_beo

PKG = "Coffee, decaf, tea, iced water & juice"


def test_parse_basic_example():
    """Covers: AC-2 (right). The §4.4 example parses; Qty 0 row dropped; blank unit is ''."""
    text = (
        "Guest Count: 70\n\n"
        "| Description | Qty | Delivery UOM |\n"
        "|---|---|---|\n"
        "| ~Beverages~ | 0 | |\n"
        "| Coffee, decaf, tea, iced water & juice | 70 | |\n"
        "| Orange juice | 70 | |\n"
        "| Fresh-brewed coffee | 2 | Gallon |\n"
        "| Oatmilk | 1 | Each |\n"
    )
    beo = parse_beo(text)
    assert beo.guests == 70
    assert beo.lines == (
        BeoLine(PKG, Fraction(70), ""),
        BeoLine("Orange juice", Fraction(70), ""),
        BeoLine("Fresh-brewed coffee", Fraction(2), "Gallon"),
        BeoLine("Oatmilk", Fraction(1), "Each"),
    )
    assert isinstance(beo.lines, tuple)
    assert all(isinstance(l.qty, Fraction) for l in beo.lines)


@pytest.mark.parametrize(
    "qty,expected",
    [
        ("2", Fraction(2)),
        ("1.5", Fraction(3, 2)),
        (".5", Fraction(1, 2)),
        ("0.1", Fraction(1, 10)),
        ("1/3", Fraction(1, 3)),
        ("7/2", Fraction(7, 2)),
    ],
)
def test_parse_qty_formats_exact(qty, expected, beo_md):
    """Covers: AC-2 (right), NFR-2. Qty decimals and fractions parse exactly into Fraction."""
    beo = parse_beo(beo_md(rows=[f"| Coffee | {qty} | Gallon |"]))
    assert beo.lines[0].qty == expected
    assert isinstance(beo.lines[0].qty, Fraction)


def test_parse_qty_zero_rows_dropped(beo_md):
    """Covers: AC-2 (boundary), EC-13. Qty 0 rows (even with empty description) are dropped."""
    beo = parse_beo(
        beo_md(
            rows=[
                "| ~Beverages~ | 0 | |",
                "| | 0 | |",
                "| Coffee | 1 | Gallon |",
                "| ~Additional Items~ | 0 | |",
                "| Coffee | 0.0 | Gallon |",
            ]
        )
    )
    assert [l.name for l in beo.lines] == ["Coffee"]


def test_parse_qty_tiny_positive_kept(beo_md):
    """Covers: AC-2 (boundary). A Qty just above 0 is kept."""
    beo = parse_beo(beo_md(rows=["| Coffee | 0.001 | Gallon |"]))
    assert beo.lines[0].qty == Fraction(1, 1000)


def test_parse_strips_name_and_unit(beo_md):
    """Covers: AC-2 (right). Name and unit are stripped but otherwise kept as written."""
    beo = parse_beo(beo_md(rows=["|   Fresh-brewed   coffee  |  2 |   Gallon   |"]))
    assert beo.lines[0].name == "Fresh-brewed   coffee"
    assert beo.lines[0].unit == "Gallon"


def test_parse_preserves_order_and_duplicates(beo_md):
    """Covers: AC-2 (right). Lines keep BEO order; duplicates are not merged."""
    beo = parse_beo(
        beo_md(rows=["| B | 1 | |", "| A | 2 | |", "| B | 3 | |"])
    )
    assert [(l.name, l.qty) for l in beo.lines] == [
        ("B", Fraction(1)),
        ("A", Fraction(2)),
        ("B", Fraction(3)),
    ]


@pytest.mark.parametrize(
    "gc",
    ["Guest Count: 70", "guest count:70", "GUEST COUNT   :   70", "  Guest Count: 70  "],
)
def test_parse_guest_count_variants(gc, beo_md):
    """Covers: AC-2 (right). Guest Count is case-insensitive and tolerates whitespace around ':'."""
    assert parse_beo(beo_md(guests_line=gc)).guests == 70


def test_parse_guest_count_one_is_minimum(beo_md):
    """Covers: AC-2 (boundary). Guest Count 1 is valid."""
    assert parse_beo(beo_md(guests_line="Guest Count: 1")).guests == 1


def test_parse_no_table_means_no_lines():
    """Covers: AC-2 (boundary), EC-28. Zero tables -> no lines."""
    beo = parse_beo("# Event\nGuest Count: 12\nSome notes\n")
    assert beo.guests == 12
    assert beo.lines == ()


def test_parse_header_only_columns_any_order_and_case():
    """Covers: AC-2 (right), §4.1. Header names are case-insensitive and may be in any order."""
    text = (
        "Guest Count: 5\n"
        "| delivery uom | QTY | description |\n"
        "|:---|---:|:---:|\n"
        "| Gallon | 3 | Coffee |\n"
    )
    beo = parse_beo(text)
    assert beo.lines == (BeoLine("Coffee", Fraction(3), "Gallon"),)


def test_parse_table_without_trailing_pipe():
    """Covers: AC-2 (right), AC-16, §4.1. The trailing pipe is optional; the leading one is required."""
    text = (
        "Guest Count: 5\n"
        "| Description | Qty | Delivery UOM\n"
        "| --- | --- | ---\n"
        "| Coffee | 3 | Gallon\n"
    )
    assert parse_beo(text).lines == (BeoLine("Coffee", Fraction(3), "Gallon"),)


def test_parse_explicit_empty_last_cell(beo_md):
    """Covers: AC-2 (boundary), §4.1, EC-34. `| Oatmilk | 1 | |` has three cells; the last one is empty."""
    beo = parse_beo(beo_md(rows=["| Oatmilk | 1 | |"]))
    assert beo.lines == (BeoLine("Oatmilk", Fraction(1), ""),)


def test_parse_table_without_leading_pipe_is_not_a_table():
    """Covers: AC-16 (wrong), EC-34, §4.1. Lines without a leading `|` are not table rows: no table, no lines, no error."""
    text = (
        "Guest Count: 5\n"
        "Description | Qty | Delivery UOM\n"
        "--- | --- | ---\n"
        "Coffee | 3 | Gallon\n"
    )
    assert parse_beo(text).lines == ()


def test_parse_row_without_leading_pipe_is_ignored(beo_md):
    """Covers: AC-16 (wrong), EC-34. A `Coffee | 3 | Gallon` line below a real table is ignored, not parsed as a row."""
    text = beo_md(rows=["| Oatmilk | 1 | Each |", "Coffee | 3 | Gallon"])
    beo = parse_beo(text)
    assert [l.name for l in beo.lines] == ["Oatmilk"]


def test_parse_row_without_leading_pipe_does_not_cause_cell_count_error(beo_md):
    """Covers: AC-16 (boundary), EC-34. A non-pipe line with the wrong number of cells is ignored rather than rejected."""
    text = beo_md(rows=["| Oatmilk | 1 | Each |", "Coffee | 3"])
    assert [l.name for l in parse_beo(text).lines] == ["Oatmilk"]


def test_parse_indented_table_rows_are_rows():
    """Covers: AC-16 (right), §4.1. A row is a line whose first NON-WHITESPACE character is `|`."""
    text = (
        "Guest Count: 5\n"
        "   | Description | Qty | Delivery UOM |\n"
        "\t|---|---|---|\n"
        "  | Coffee | 3 | Gallon |\n"
    )
    assert parse_beo(text).lines == (BeoLine("Coffee", Fraction(3), "Gallon"),)


def test_parse_ignores_non_table_lines():
    """Covers: AC-2 (right), §4.1. Headings, notes and blank lines are ignored, including Special Instructions."""
    text = (
        "# BEO 1\n\nGuest Count: 40\n\nNotes: leave iced water\n\n"
        "| Description | Qty | Delivery UOM |\n|---|---|---|\n| Coffee | 1 | Gallon |\n\n"
        "Special Instructions: Oatmilk please\n"
    )
    beo = parse_beo(text)
    assert beo.guests == 40
    assert [l.name for l in beo.lines] == ["Coffee"]


@pytest.mark.parametrize(
    "text",
    [
        "| Description | Qty | Delivery UOM |\n|---|---|---|\n| Coffee | 1 | Gallon |\n",
        "Guest Count: 70\nGuest Count: 70\n",
        "Guest Count: 70 guests\n",
        "Guest Count: 70\nguest count: 80\n",
        "Guest Count: 0\n",
        "Guest Count: -5\n",
        "Guest Count: 2.5\n",
        "Guest Count: abc\n",
        "Guest Count:\n",
    ],
    ids=[
        "missing",
        "duplicate-same",
        "trailing-text",
        "duplicate-different",
        "zero",
        "negative",
        "decimal",
        "non-numeric",
        "empty",
    ],
)
def test_parse_guest_count_errors(text):
    """Covers: AC-2 (wrong), EC-27. Missing, duplicate or invalid Guest Count -> BeoError."""
    with pytest.raises(BeoError):
        parse_beo(text)


@pytest.mark.parametrize("qty", ["-1", "abc", "", "1/0", "-1/2", "1,5"])
def test_parse_invalid_qty(qty, beo_md):
    """Covers: AC-2 (wrong), EC-27. Negative or invalid Qty -> BeoError (1/0 and '' are implied invalid)."""
    with pytest.raises(BeoError):
        parse_beo(beo_md(rows=[f"| Coffee | {qty} | Gallon |"]))


def test_parse_invalid_qty_reports_line():
    """Covers: AC-2 (wrong), EC-27. BeoError.line is the 1-based line of the bad row."""
    text = "Guest Count: 5\n\n| Description | Qty | Delivery UOM |\n|---|---|---|\n| Coffee | abc | Gallon |\n"
    with pytest.raises(BeoError) as ei:
        parse_beo(text)
    assert ei.value.line == 5


def test_parse_empty_description_with_positive_qty(beo_md):
    """Covers: AC-2 (wrong), EC-27. Empty Description with Qty 2 -> BeoError."""
    with pytest.raises(BeoError):
        parse_beo(beo_md(rows=["|  | 2 | Gallon |"]))


def test_parse_second_table_rejected(beo_md):
    """Covers: AC-2 (wrong), EC-27. A second table -> BeoError."""
    text = beo_md(rows=["| Coffee | 1 | Gallon |"]) + "\nnotes\n\n" + (
        "| Description | Qty | Delivery UOM |\n|---|---|---|\n| Decaf | 1 | Gallon |\n"
    )
    with pytest.raises(BeoError) as ei:
        parse_beo(text)
    assert ei.value.line == 9


@pytest.mark.parametrize(
    "header,ncols",
    [
        ("| Description | Qty | Delivery UOM | Price |", 4),
        ("| Description | Qty |", 2),
        ("| Item | Qty | Delivery UOM |", 3),
        ("| Description | Qty | Qty |", 3),
    ],
    ids=["extra-column", "missing-column", "wrong-name", "duplicate-column"],
)
def test_parse_bad_header(header, ncols):
    """Covers: AC-2 (wrong), AC-16, §4.1/§4.4. Header must be exactly the column set; separator and data rows
    have the same cell count as the header, so only the header rule can fail. BeoError.line is the header line."""
    sep = "|" + "---|" * ncols
    row = "|" + " x |" * ncols
    text = f"Guest Count: 5\n{header}\n{sep}\n{row}\n"
    with pytest.raises(BeoError) as ei:
        parse_beo(text)
    assert ei.value.line == 2


def test_parse_header_case_and_whitespace_insensitive():
    """Covers: AC-2 (right), §4.1. Header names match case-insensitively after stripping."""
    text = "Guest Count: 5\n|  DESCRIPTION  |qty|  delivery uom|\n|---|---|---|\n| Coffee | 3 | Gallon |\n"
    assert parse_beo(text).lines == (BeoLine("Coffee", Fraction(3), "Gallon"),)


# --- BeoError.line (AC-16, EC-34) ---
def test_beo_error_line_second_guest_count():
    """Covers: AC-16 (wrong), EC-34. A second Guest Count line on line 3 -> BeoError.line == 3."""
    with pytest.raises(BeoError) as ei:
        parse_beo("Guest Count: 70\n\nGuest Count: 80\n")
    assert ei.value.line == 3


def test_beo_error_line_missing_guest_count_is_none():
    """Covers: AC-16 (wrong), AC-2, EC-34. A missing Guest Count -> BeoError.line is None."""
    with pytest.raises(BeoError) as ei:
        parse_beo("# nothing here\n\nnotes\n")
    assert ei.value.line is None


def test_beo_error_line_invalid_guest_count():
    """Covers: AC-16 (wrong), EC-27. The invalid Guest Count line number is reported."""
    with pytest.raises(BeoError) as ei:
        parse_beo("# BEO\nGuest Count: 0\n")
    assert ei.value.line == 2


def test_beo_error_line_bad_separator_row():
    """Covers: AC-16 (wrong), §4.4. A bad separator row reports its own line."""
    text = "Guest Count: 5\n| Description | Qty | Delivery UOM |\n| abc | def | ghi |\n| Coffee | 1 | Gallon |\n"
    with pytest.raises(BeoError) as ei:
        parse_beo(text)
    assert ei.value.line == 3


def test_beo_error_line_wrong_cell_count_row(beo_md):
    """Covers: AC-16 (wrong), EC-34. `| Oatmilk | 1 |` (two cells) -> BeoError on that row's line."""
    text = beo_md(rows=["| Coffee | 1 | Gallon |", "| Oatmilk | 1 |"])
    with pytest.raises(BeoError) as ei:
        parse_beo(text)
    assert ei.value.line == 6


def test_beo_error_line_empty_description(beo_md):
    """Covers: AC-16 (wrong), EC-27. Empty Description with Qty > 0 reports the data row line."""
    with pytest.raises(BeoError) as ei:
        parse_beo(beo_md(rows=["| Coffee | 1 | Gallon |", "|  | 2 | Gallon |"]))
    assert ei.value.line == 6


def test_beo_error_line_negative_qty(beo_md):
    """Covers: AC-16 (wrong), EC-27. Negative Qty reports the data row line."""
    with pytest.raises(BeoError) as ei:
        parse_beo(beo_md(rows=["| Coffee | -1 | Gallon |"]))
    assert ei.value.line == 5


def test_parse_missing_separator_row():
    """Covers: AC-2 (wrong), §4.1. Second row must be a separator row."""
    text = "Guest Count: 5\n| Description | Qty | Delivery UOM |\n| Coffee | 1 | Gallon |\n"
    with pytest.raises(BeoError):
        parse_beo(text)


def test_parse_separator_with_text_rejected():
    """Covers: AC-2 (wrong), §4.1. Separator cells may only contain '-', ':' and spaces."""
    text = "Guest Count: 5\n| Description | Qty | Delivery UOM |\n|---|abc|---|\n| Coffee | 1 | Gallon |\n"
    with pytest.raises(BeoError):
        parse_beo(text)


def test_parse_empty_separator_cell_rejected():
    """Covers: AC-2 (wrong), §4.1. Every separator cell must be non-empty."""
    text = "Guest Count: 5\n| Description | Qty | Delivery UOM |\n|---||---|\n| Coffee | 1 | Gallon |\n"
    with pytest.raises(BeoError):
        parse_beo(text)


@pytest.mark.parametrize("row", ["| Coffee | 1 |", "| Coffee | 1 | Gallon | extra |"])
def test_parse_row_cell_count_mismatch(row, beo_md):
    """Covers: AC-2 (wrong), §4.1. Every row must have as many cells as the header."""
    with pytest.raises(BeoError):
        parse_beo(beo_md(rows=[row]))

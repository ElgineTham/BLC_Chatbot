"""main and the end-to-end example (spec 002 AC-12, EC-30 header). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
import pytest

from pull_sheet import build_pull_sheet, format_pull_sheet, main, parse_beo

PKG = "Coffee, decaf, tea, iced water & juice"


def test_ec30_header_still_shows_guest_count_in_cli(tmp_path, capsys, write_dir, beo_md):
    """Covers: AC-14 (right), EC-30, AC-12. Guest Count 50 + package 70: first output line says 50, cups are 120."""
    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text(beo_md("Guest Count: 50", [f"| {PKG} | 70 | |"]), encoding="utf-8")
    assert main([str(beo), "--rules", str(base)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "Pull sheet for 50 guests"
    assert "- hot-cups: 120\n" in out
    assert "- cold-cups: 120\n" in out


def test_end_to_end_spec_example(tmp_path, make_catalog, EXAMPLE_BEO, EXAMPLE_OUT):
    """Covers: AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-11 (right), EC-4. §4.4 BEO + Cascade line yields the §4.6 text."""
    cat = make_catalog(tmp_path)
    out = format_pull_sheet(build_pull_sheet(cat, parse_beo(EXAMPLE_BEO)))
    assert out == EXAMPLE_OUT


def test_main_success(tmp_path, capsys, write_dir, EXAMPLE_BEO, EXAMPLE_OUT):
    """Covers: AC-12 (right). main prints the formatted sheet to stdout and returns 0, even with skipped lines."""
    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text(EXAMPLE_BEO, encoding="utf-8")
    rc = main([str(beo), "--rules", str(base)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == EXAMPLE_OUT
    assert captured.err == ""


def test_main_empty_beo_prints_none(tmp_path, capsys, write_dir):
    """Covers: AC-12 (boundary), EC-28. A BEO with no table -> '- (none)' and exit 0."""
    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text("Guest Count: 12\n", encoding="utf-8")
    assert main([str(beo), "--rules", str(base)]) == 0
    assert capsys.readouterr().out == "Pull sheet for 12 guests\n\nBeverages\n- (none)\n"


def _assert_one_error_line(captured):
    assert captured.out == ""
    lines = captured.err.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("error: ")


def test_main_bad_rules_dir(tmp_path, capsys, EXAMPLE_BEO):
    """Covers: AC-12 (wrong). Missing rules dir -> one 'error: ' line on stderr, empty stdout, return 1."""
    beo = tmp_path / "event.md"
    beo.write_text(EXAMPLE_BEO, encoding="utf-8")
    rc = main([str(beo), "--rules", str(tmp_path / "nope")])
    assert rc == 1
    _assert_one_error_line(capsys.readouterr())


def test_main_invalid_rules_file(tmp_path, capsys, write_dir, EXAMPLE_BEO):
    """Covers: AC-12 (wrong). Invalid rules JSON -> error line, return 1."""
    base = write_dir(tmp_path, rules='{"cambros": [,]}')
    beo = tmp_path / "event.md"
    beo.write_text(EXAMPLE_BEO, encoding="utf-8")
    assert main([str(beo), "--rules", str(base)]) == 1
    _assert_one_error_line(capsys.readouterr())


def test_main_bad_beo(tmp_path, capsys, write_dir):
    """Covers: AC-12 (wrong). Invalid BEO (no Guest Count) -> error line, return 1."""
    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text("| Description | Qty | Delivery UOM |\n|---|---|---|\n| Coffee | 1 | Gallon |\n", encoding="utf-8")
    assert main([str(beo), "--rules", str(base)]) == 1
    _assert_one_error_line(capsys.readouterr())


def test_main_missing_beo_file(tmp_path, capsys, write_dir):
    """Covers: AC-12 (wrong). Missing BEO file -> error line, return 1."""
    base = write_dir(tmp_path)
    assert main([str(tmp_path / "missing.md"), "--rules", str(base)]) == 1
    _assert_one_error_line(capsys.readouterr())


def test_main_beo_is_directory(tmp_path, capsys, write_dir):
    """Covers: AC-12 (wrong). An unreadable BEO path (a directory) -> error line, return 1."""
    base = write_dir(tmp_path)
    assert main([str(tmp_path), "--rules", str(base)]) == 1
    _assert_one_error_line(capsys.readouterr())


def test_main_no_args_is_usage_error(capsys):
    """Covers: AC-12 (wrong). Wrong arguments -> argparse exit code 2."""
    with pytest.raises(SystemExit) as ei:
        main([])
    assert ei.value.code == 2


def test_main_unknown_option_is_usage_error(tmp_path, capsys, EXAMPLE_BEO):
    """Covers: AC-12 (wrong). Unknown option -> argparse exit code 2."""
    beo = tmp_path / "event.md"
    beo.write_text(EXAMPLE_BEO, encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        main([str(beo), "--bogus"])
    assert ei.value.code == 2


def test_main_writes_nothing(tmp_path, write_dir, EXAMPLE_BEO):
    """Covers: AC-12 (right), §3. The CLI writes no files (rules dir and BEO unchanged)."""
    base = write_dir(tmp_path)
    beo = tmp_path / "event.md"
    beo.write_text(EXAMPLE_BEO, encoding="utf-8")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    snapshot = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    main([str(beo), "--rules", str(base)])
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == snapshot

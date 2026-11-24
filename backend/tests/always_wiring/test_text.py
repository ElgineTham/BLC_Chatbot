"""Spec 045 section 6.2 TEXT (AC-7) and the import check of AC-8. Unit, no model, no file."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ITEMS = ("Black linens", "Black napkins", "Purple napkins")


def _question(text):
    """The last line of the text (the question of a need_info reply)."""
    return text.strip().splitlines()[-1]


def test_text_1_tables_scope(run_tool):
    """Covers: AC-7 (right), TEXT-1. about tables, tables 4: bus tubs, towels, linens 9, purple 8; no black
    napkins."""
    text = run_tool({"about": "tables", "tables": 4}).text
    assert "Bus tubs" in text and "Towels" in text
    assert "Black linens: 9" in text
    assert "Purple napkins: 8" in text
    assert "Black napkins" not in text
    assert "black napkins" not in text.lower()


def test_text_2_drip_tray_scope(run_tool):
    """Covers: AC-7 (right), TEXT-2. about drip_trays, drip_trays 3: bus tubs, towels, black napkins 3; no
    linens, no purple napkins."""
    text = run_tool({"about": "drip_trays", "drip_trays": 3}).text
    assert "Bus tubs" in text and "Towels" in text
    assert "Black napkins: 3" in text
    assert "Black linens" not in text
    assert "Purple napkins" not in text


def test_text_3_both_need_drip_trays(run_tool):
    """Covers: AC-7 (right), TEXT-3. about both, tables 4 only: known counts listed, ends with a question that
    asks how many drip trays."""
    r = run_tool({"about": "both", "tables": 4})
    text = r.text
    assert r.status == "need_info"
    assert "Bus tubs" in text and "Towels" in text
    assert "Black linens: 9" in text and "Purple napkins: 8" in text
    assert text.strip().endswith("?")
    assert "how many" in text.lower()
    assert "drip trays" in _question(text).lower()
    assert "Black napkins" not in text


def test_text_4_tables_scope_asks_tables_only(run_tool):
    """Covers: AC-7 (wrong), TEXT-4. about tables, no tables, drip_trays 3: question asks how many tables and
    never mentions drip trays; no counts are named."""
    r = run_tool({"about": "tables", "drip_trays": 3})
    text = r.text
    assert r.status == "need_info"
    assert "Bus tubs" in text and "Towels" in text
    assert text.strip().endswith("?")
    assert "how many" in text.lower() and "tables" in text.lower()
    assert "drip trays" not in text.lower()
    for name in ITEMS:
        assert name not in text


def test_text_drip_scope_asks_drip_trays_only(run_tool):
    """Covers: AC-7 (wrong). Extra: about drip_trays with no drip_trays asks for drip trays and never tables."""
    text = run_tool({"about": "drip_trays", "tables": 4}).text
    assert "Bus tubs" in text and "Towels" in text
    assert text.strip().endswith("?")
    assert "how many" in text.lower() and "drip trays" in text.lower()
    assert "tables" not in text.lower()
    for name in ITEMS:
        assert name not in text


def test_text_5_both_neither(run_tool):
    """Covers: AC-7 (wrong), TEXT-5. about both, nothing given: bus tubs, towels, one question naming tables and
    drip trays."""
    text = run_tool({"about": "both"}).text
    assert "Bus tubs" in text and "Towels" in text
    assert text.strip().endswith("?")
    q = _question(text).lower()
    assert "how many" in text.lower()
    assert "tables" in q and "drip trays" in q


def test_text_both_only_drip_trays_given(run_tool):
    """Covers: AC-7 (right). Extra: about both with drip_trays 3 lists black napkins 3 and asks for tables."""
    text = run_tool({"about": "both", "drip_trays": 3}).text
    assert "Black napkins: 3" in text
    assert "Black linens" not in text and "Purple napkins" not in text
    assert "tables" in _question(text).lower()
    assert text.strip().endswith("?")


def test_text_ok_ends_without_question(run_tool):
    """Covers: AC-7 (boundary). An ok text asks nothing."""
    assert not run_tool({"about": "both", "tables": 2, "drip_trays": 3}).text.strip().endswith("?")


def test_text_zero_counts_listed(run_tool):
    """Covers: AC-7 (boundary). Zeros are listed in the scope's items only."""
    text = run_tool({"about": "tables", "tables": 0}).text
    assert "Black linens: 0" in text and "Purple napkins: 0" in text
    assert "Black napkins" not in text
    text = run_tool({"about": "drip_trays", "drip_trays": 0}).text
    assert "Black napkins: 0" in text


def test_text_count_order_in_both(run_tool):
    """Covers: AC-7 (right). Counts appear in ALWAYS_COUNT_ITEMS order."""
    text = run_tool({"about": "both", "tables": 2, "drip_trays": 3}).text
    for name, n in (("Black linens", 5), ("Black napkins", 3), ("Purple napkins", 4)):
        assert f"{name}: {n}" in text
    order = [text.index(n) for n in ITEMS]
    assert order == sorted(order)


@pytest.mark.parametrize("args", [
    {"about": "both", "tables": 4},
    {"about": "tables"},
    {"about": "drip_trays", "tables": 1},
])
def test_text_bus_tubs_and_towels_in_every_question(run_tool, args):
    """Covers: AC-7 (right). Bus tubs and towels are listed in every reply, including the ones that ask."""
    r = run_tool(args)
    assert r.status == "need_info"
    assert "Bus tubs" in r.text and "Towels" in r.text


def test_text_invalid_as_spec_044(run_tool):
    """Covers: AC-7 (wrong). An invalid text starts with 'invalid', names the field and shows the example
    format (spec 044 section 4.3)."""
    r = run_tool({"about": "tables", "tables": "two"})
    assert r.status == "invalid"
    assert r.text.lower().startswith("invalid")
    assert "tables" in r.text
    assert '"tables"' in r.text and '"drip_trays"' in r.text


def test_text_invalid_non_mapping(run_tool):
    """Covers: AC-7 (wrong). Non-mapping args give the invalid text with the example format."""
    r = run_tool(None)
    assert r.text.lower().startswith("invalid")
    assert '"tables"' in r.text and '"drip_trays"' in r.text


def test_pkg_import_leaves_out_langchain_core():
    """Covers: AC-8 (right), SCOPE-14. A fresh interpreter imports the package without langchain_core."""
    code = (
        "import sys, blc.tools.always_tools; "
        "sys.exit(1 if 'langchain_core' in sys.modules else 0)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ":".join(p for p in sys.path if p)},
    )
    assert proc.returncode == 0, proc.stderr

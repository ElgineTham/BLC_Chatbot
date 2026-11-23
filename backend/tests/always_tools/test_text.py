"""Spec 044 section 6.3 TEXT and 6.4 PKG."""
import subprocess
import sys

import pytest

import blc.tools.always_tools as pkg
from blc.tools.always_tools import (
    ALWAYS_CHECK_ITEMS,
    ALWAYS_COUNT_ITEMS,
    ALWAYS_STATUSES,
    ALWAYS_TOOL_NAME,
)


def test_text_1_ok(run):
    """Covers: AC-7 (right), TEXT-1. Checks and counts listed, counts in order."""
    text = run({"tables": 2, "drip_trays": 3}).text
    assert "Bus tubs" in text
    assert "Towels" in text
    assert "Black linens: 5" in text
    assert "Black napkins: 3" in text
    assert "Purple napkins: 4" in text
    order = [text.index(n) for n in ("Black linens", "Black napkins", "Purple napkins")]
    assert order == sorted(order)


def test_text_2_zero_count_listed(run):
    """Covers: AC-7 (boundary), TEXT-2. Zero counts are listed."""
    text = run({"tables": 1, "drip_trays": 0}).text
    assert "Black napkins: 0" in text
    assert "Black linens: 3" in text
    assert "Purple napkins: 2" in text


def test_text_2_all_zero_listed(run):
    """Covers: AC-7 (boundary). Extra: 0 tables and 0 trays lists all zeros."""
    text = run({"tables": 0, "drip_trays": 0}).text
    for name in ("Black linens", "Black napkins", "Purple napkins"):
        assert f"{name}: 0" in text


@pytest.mark.parametrize(
    "args,must_have",
    [
        ({"drip_trays": 3}, ["tables"]),
        ({"tables": 2}, ["drip trays"]),
        ({}, ["tables", "drip trays"]),
    ],
)
def test_text_3_need_info(run, args, must_have):
    """Covers: AC-7 (wrong), TEXT-3. One question naming the missing item(s)."""
    r = run(args)
    assert r.status == "need_info"
    text = r.text.strip()
    assert text.endswith("?")
    assert "how many" in text.lower()
    for word in must_have:
        assert word in text.lower()


@pytest.mark.parametrize(
    "args,field",
    [
        ({"tables": "two", "drip_trays": 3}, "tables"),
        ({"tables": 2, "drip_trays": -1}, "drip_trays"),
    ],
)
def test_text_4_invalid(run, args, field):
    """Covers: AC-7 (wrong), TEXT-4. Starts with 'invalid', names field, shows example format."""
    r = run(args)
    assert r.status == "invalid"
    assert r.text.lower().startswith("invalid")
    assert field in r.text
    assert '"tables"' in r.text
    assert '"drip_trays"' in r.text


def test_text_invalid_non_mapping_has_format(run):
    """Covers: AC-7 (wrong). Extra: non-mapping args still show the example format."""
    r = run(None)
    assert r.text.lower().startswith("invalid")
    assert '"tables"' in r.text and '"drip_trays"' in r.text


def test_pkg_1_no_langchain_core():
    """Covers: AC-8 (right), PKG-1. Fresh interpreter imports the package without langchain_core."""
    code = (
        "import sys, blc.tools.always_tools; "
        "sys.exit(1 if 'langchain_core' in sys.modules else 0)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": ":".join(p for p in sys.path if p)},
    )
    assert proc.returncode == 0, proc.stderr


def test_pkg_2_constants():
    """Covers: AC-1 (right), PKG-2. Public constants have the specified values."""
    assert ALWAYS_TOOL_NAME == "calculate_always_items"
    assert ALWAYS_STATUSES == ("ok", "need_info", "invalid")
    assert ALWAYS_CHECK_ITEMS == ("bus tubs", "towels")
    assert ALWAYS_COUNT_ITEMS == ("black linens", "black napkins", "purple napkins")


def test_pkg_result_is_frozen(run):
    """Covers: AC-1 (wrong). Extra: AlwaysResult is a frozen dataclass."""
    r = run({"tables": 1, "drip_trays": 1})
    with pytest.raises(Exception):
        r.status = "invalid"
    assert hasattr(pkg, "AlwaysResult")


def test_status_always_in_allowed(run):
    """Covers: AC-4 (right). Extra: every outcome uses a status from ALWAYS_STATUSES."""
    for args in ({}, {"tables": 1, "drip_trays": 1}, {"tables": -1}, None):
        assert run(args).status in ALWAYS_STATUSES

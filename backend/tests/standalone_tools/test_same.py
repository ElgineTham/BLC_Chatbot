"""Spec 024 section 6.3 SAME: snapshot replays and CLI byte-identity (AC-8, AC-9, AC-10)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "docs" / "specs"
BEV_SNAPSHOT = SPECS / "024-bev-snapshot.jsonl"


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _frac(x):
    return None if x is None else str(x)


def _bev_actual(case):
    from blc.tools.bev_tools import DrinkRequest, calculate_bev_item
    i = case["input"]
    reqs = [DrinkRequest(d["menu"], d["quantity"], d["unit"]) for d in i["drinks"]]
    r = calculate_bev_item(i["item"], reqs, i["guests"])
    return {
        "status": r.status, "text": r.text,
        "drinks": [[d.drink, _frac(d.amount), d.unit, d.from_guests] for d in r.drinks],
        "lines": [[l.supply, l.quantity, list(l.reasons)] for l in r.lines],
        "not_on_menu": list(r.not_on_menu), "gallons_each": r.gallons_each, "cups_each": r.cups_each,
    }


def test_bev_snapshot_replay_identical(need_pull_sheet_data):
    """Covers: SAME-1, AC-8 (right). Every recorded bev case reproduces its recorded output exactly."""
    cases = read_jsonl(BEV_SNAPSHOT)
    assert len(cases) == 5085
    bad = []
    for c in cases:
        try:
            actual = _bev_actual(c)
        except Exception as e:  # a crash is a mismatch
            actual = {"raised": repr(e)}
        if actual != c["output"]:
            bad.append((c["input"], c["output"], actual))
    assert not bad, "%d mismatches; first: %r" % (len(bad), bad[:3])


def test_bev_snapshot_covers_every_status():
    """Covers: SAME-1, AC-8 (boundary). Guard: the snapshot includes error and need_info cases, not just ok."""
    statuses = {c["output"]["status"] for c in read_jsonl(BEV_SNAPSHOT)}
    assert "ok" in statuses and "need_info" in statuses and len(statuses) >= 3


# Spec 041: the recipe snapshot replay and the CLI byte-identity cases were deleted with their baseline files.


@pytest.mark.integration
def test_cli_missing_file_fails(tmp_path):
    """Covers: SAME-5, AC-10 (wrong). Missing BEO: one 'error: ' line on stderr, empty stdout, exit 1."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run([sys.executable, "backend/scripts/pull_sheet.py", str(tmp_path / "missing.md")],
                          capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=120)
    assert proc.returncode == 1
    assert proc.stdout == ""
    lines = proc.stderr.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("error: ")

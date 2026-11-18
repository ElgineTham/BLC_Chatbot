"""AC-13, NFR-1, NFR-2, NFR-4 and contract constants (spec 002). Moved from tests/test_pull_sheet.py.

Shared helpers come from conftest.py as fixtures.
"""
import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pull_sheet
from pull_sheet import (
    DEFAULT_RULES_DIR,
    EACH,
    GALLON,
    GUESTS_PER_GALLON,
    MENU_FILE,
    NOT_ON_MENU,
    PER_VALUES,
    RULES_FILE,
    TICK,
    UNKNOWN_UNIT,
    BeoError,
    RuleFileError,
    build_pull_sheet,
    format_pull_sheet,
    load_catalog,
    parse_beo,
)

PKG = "Coffee, decaf, tea, iced water & juice"
SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "scripts")


def test_contract_constants():
    """Covers: §3 contract (right). Constants have the documented values."""
    assert GALLON == "gallon"
    assert EACH == "each"
    assert GUESTS_PER_GALLON == 25
    assert tuple(PER_VALUES) == ("event", "guest", "guest+extra", "item", "unit")
    assert TICK == "✓"
    assert NOT_ON_MENU == "not on beverage menu"
    assert UNKNOWN_UNIT == "unknown unit"
    assert MENU_FILE == "menu/beverages.json"
    assert RULES_FILE == "rules/beverages.json"
    assert DEFAULT_RULES_DIR == pull_sheet.ROOT / "data" / "pull_sheet"
    assert issubclass(RuleFileError, ValueError)
    assert issubclass(BeoError, ValueError)


def test_ec31_item_order_stable_across_hash_seeds(tmp_path, write_dir, mk_beo):
    """Covers: AC-13 (right), AC-15, EC-31. Separate Python processes with different PYTHONHASHSEED values give
    the identical PullSheet and text, equal to the in-process result."""
    base = write_dir(tmp_path)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from pathlib import Path; from fractions import Fraction; import pull_sheet as p; "
        "cat = p.load_catalog(Path(sys.argv[2])); "
        "beo = p.Beo(70, (p.BeoLine(sys.argv[3], Fraction(70), ''),)); "
        "sheet = p.build_pull_sheet(cat, beo); "
        "print(repr(sheet)); print(p.format_pull_sheet(sheet))"
    )
    outs = []
    for seed in ("0", "1", "2", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", code, SCRIPTS_DIR, str(base), PKG],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout)
    assert len(set(outs)) == 1
    here = build_pull_sheet(load_catalog(base), mk_beo(70, [(PKG, 70, "")]))
    assert outs[0].startswith(repr(here) + "\n")


def test_deterministic_same_inputs_same_output(tmp_path, make_catalog, EXAMPLE_BEO):
    """Covers: AC-13 (right). Same catalog and BEO -> equal PullSheet and identical text; fresh catalogs agree."""
    beo = parse_beo(EXAMPLE_BEO)
    cat1 = make_catalog(tmp_path / "a")
    cat2 = make_catalog(tmp_path / "b")
    s1 = build_pull_sheet(cat1, beo)
    s2 = build_pull_sheet(cat1, beo)
    s3 = build_pull_sheet(cat2, beo)
    assert s1 == s2 == s3
    assert format_pull_sheet(s1) == format_pull_sheet(s2) == format_pull_sheet(s3)


def test_build_does_not_mutate_inputs(tmp_path, make_catalog, mk_beo, EXAMPLE_BEO):
    """Covers: NFR-4 (right). build_pull_sheet leaves the Beo and catalog unchanged (a second build is identical)."""
    cat = make_catalog(tmp_path)
    beo = parse_beo(EXAMPLE_BEO)
    snapshot = copy.deepcopy(beo)
    first = build_pull_sheet(cat, beo)
    assert beo == snapshot
    assert beo.lines == snapshot.lines
    second = build_pull_sheet(cat, beo)
    assert first == second
    other = build_pull_sheet(cat, mk_beo(10, [("Coffee", 1, "Gallon")]))
    assert build_pull_sheet(cat, beo) == first
    assert other.guests == 10


def test_parse_is_deterministic(EXAMPLE_BEO):
    """Covers: AC-13 (right). parse_beo of the same text twice gives equal results."""
    assert parse_beo(EXAMPLE_BEO) == parse_beo(EXAMPLE_BEO)


def test_import_does_not_load_llm_stack():
    """Covers: NFR-1 (right). Importing pull_sheet imports no langchain, chromadb or ollama."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import pull_sheet; "
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('langchain', 'langchain_core', 'langchain_chroma', 'langchain_ollama', 'chromadb', 'ollama')]; "
        "print(','.join(sorted(bad))); sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code, SCRIPTS_DIR], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

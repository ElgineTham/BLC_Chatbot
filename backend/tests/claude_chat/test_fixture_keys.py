"""Spec 039 section 6.5 (MIGRATE-5, MIGRATE-6), AC-4: no pytest fixture under backend/tests/ returns, yields or
parametrizes an API key value. Static scan with `ast` over every test file, plus a dynamic check of the key-checking
fixtures in docker/ and gemini_migration/ (the claude_chat/ ones are checked in test_migrate.py). Unit tests; no network.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
KEY_NAMES = ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY")


# ---- scan helpers (static)

def _reads_key_from_env(expr: ast.AST, tainted: set[str]) -> bool:
    """True when the expression reads either key from the environment, or uses a name that holds one."""
    has_env = has_key = False
    for n in ast.walk(expr):
        if isinstance(n, ast.Attribute) and n.attr in ("environ", "getenv"):
            has_env = True
        if isinstance(n, ast.Name) and n.id in ("environ", "getenv"):
            has_env = True
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in KEY_NAMES:
            has_key = True
        if isinstance(n, ast.Name) and n.id in tainted:
            return True
    return has_env and has_key


def _is_fixture(fn: ast.AST) -> bool:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for d in fn.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if (isinstance(target, ast.Attribute) and target.attr == "fixture") or (
            isinstance(target, ast.Name) and target.id == "fixture"
        ):
            return True
    return False


def _tainted_names(scope: ast.AST) -> set[str]:
    tainted: set[str] = set()
    for _ in range(3):  # propagate through a few assignment hops
        for n in ast.walk(scope):
            if isinstance(n, ast.Assign) and _reads_key_from_env(n.value, tainted):
                for t in n.targets:
                    for name in ast.walk(t):
                        if isinstance(name, ast.Name):
                            tainted.add(name.id)
            elif isinstance(n, ast.NamedExpr) and _reads_key_from_env(n.value, tainted):
                tainted.add(n.target.id)
    return tainted


def key_leaks(source: str) -> list[str]:
    """Descriptions of fixtures that return/yield a key, and parametrize/params that carry one."""
    tree = ast.parse(source)
    module_tainted = _tainted_names(tree)
    leaks = []
    for node in ast.walk(tree):
        if _is_fixture(node):
            tainted = module_tainted | _tainted_names(node)
            for n in ast.walk(node):
                if isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom)) and n.value is not None:
                    if _reads_key_from_env(n.value, tainted):
                        leaks.append(f"fixture {node.name} returns/yields a key (line {n.lineno})")
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and _reads_key_from_env(d, module_tainted):
                    leaks.append(f"fixture {node.name} params carry a key (line {d.lineno})")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "parametrize" and _reads_key_from_env(node, module_tainted):
                leaks.append(f"parametrize carries a key (line {node.lineno})")
    return leaks


def _test_files():
    files = sorted(p for p in TESTS_DIR.rglob("*.py") if p.resolve() != THIS_FILE)
    assert len(files) > 50  # guards a vacuous pass
    return files


# ---- MIGRATE-6 / AC-4

def test_no_fixture_returns_or_parametrizes_a_key():
    """Covers: AC-4 (wrong), MIGRATE-6. Across every file under backend/tests/, no fixture returns or yields
    os.environ[...] / os.getenv(...) of either key (directly or through a variable), and no parametrize carries one."""
    hits = []
    for path in _test_files():
        for leak in key_leaks(path.read_text(encoding="utf-8")):
            hits.append(f"{path.relative_to(TESTS_DIR)}: {leak}")
    assert hits == []


def test_scan_detects_a_returned_key():
    """Covers: AC-4 (boundary), MIGRATE-6. The detector flags a fixture returning a key read from the environment,
    directly and via a variable, a yield, and a parametrize; it passes a presence-only fixture."""
    returns_var = (
        "import os, pytest\n@pytest.fixture\ndef k():\n"
        "    key = os.environ.get('GOOGLE_API_KEY', '').strip()\n    return key\n"
    )
    returns_direct = "import os, pytest\n@pytest.fixture\ndef k():\n    return os.environ['ANTHROPIC_API_KEY']\n"
    yields = "import os, pytest\n@pytest.fixture\ndef k():\n    yield os.getenv('ANTHROPIC_API_KEY')\n"
    param = "import os, pytest\n@pytest.mark.parametrize('k', [os.environ['GOOGLE_API_KEY']])\ndef test_x(k): pass\n"
    presence = (
        "import os, pytest\n@pytest.fixture\ndef k():\n"
        "    if not os.environ.get('GOOGLE_API_KEY', '').strip():\n        pytest.skip('no')\n    return True\n"
    )
    literal_env = "import pytest\n@pytest.fixture\ndef e():\n    return {'GOOGLE_API_KEY': 'invalid'}\n"
    for src in (returns_var, returns_direct, yields, param):
        assert key_leaks(src), src
    assert key_leaks(presence) == []
    assert key_leaks(literal_env) == []


# ---- MIGRATE-5 / AC-4 (dynamic, for the fixtures outside claude_chat/)

SENTINEL_A = "sk-ant-SENTINEL-333"
SENTINEL_G = "goog-SENTINEL-444"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"_spec039_{path.parent.name}_conftest", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raw_function(obj):
    """The undecorated function behind a pytest fixture across pytest versions."""
    for attr in ("_get_wrapped_function", ):
        getter = getattr(obj, attr, None)
        if callable(getter):
            return getter()
    wrapped = getattr(obj, "__pytest_wrapped__", None)
    if wrapped is not None:
        return wrapped.obj
    return obj if callable(obj) else None


@pytest.mark.parametrize(
    "rel,name",
    [
        ("docker/conftest.py", "gemini_key"),
        ("docker/conftest.py", "anthropic_key"),
        ("gemini_migration/conftest.py", "live_key"),
    ],
)
def test_key_checking_fixtures_elsewhere_return_no_sentinel(monkeypatch, rel, name):
    """Covers: AC-4 (wrong), MIGRATE-5. With sentinel keys set, the key-checking fixtures in docker/ and
    gemini_migration/ return nothing that contains a sentinel."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL_A)
    monkeypatch.setenv("GOOGLE_API_KEY", SENTINEL_G)
    fn = _raw_function(getattr(_load(TESTS_DIR / rel), name))
    if fn is None:
        pytest.skip("cannot unwrap the fixture on this pytest version")
    value = fn()
    rendered = repr(value) + str(value)
    assert SENTINEL_A not in rendered
    assert SENTINEL_G not in rendered

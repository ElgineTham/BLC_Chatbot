"""Shared fixtures for the spec 024 tests (standalone bev_tools / recipe_tools). Written from the spec only.

Test files do not import this module (several conftest.py files exist, so the name is ambiguous);
they use the fixtures below. Import checks run in a fresh interpreter (sys.executable -c ...) with
src/ on the path and PYTHONPATH unset, so modules loaded by other tests never affect them.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FORBIDDEN_TOP = ["langchain", "langchain_core", "langchain_ollama", "langchain_chroma",
                 "langgraph", "chromadb", "ollama"]

_REPORT = """
import json, sys
loaded = sorted(sys.modules)
tops = {m.split('.')[0] for m in loaded}
print("@@REPORT@@" + json.dumps({
    "pull_sheet": [m for m in loaded if m == "blc.pull_sheet" or m.startswith("blc.pull_sheet.")],
    "forbidden": sorted(tops & set(%r)),
}))
"""


@pytest.fixture
def fresh():
    """Run code in a fresh interpreter; assert it exits 0; return {"pull_sheet": [...], "forbidden": [...]}."""
    def _run(code):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        full = "import sys\nsys.path.insert(0, %r)\n" % str(SRC) + code + _REPORT % (FORBIDDEN_TOP,)
        proc = subprocess.run([sys.executable, "-c", full], capture_output=True, text=True,
                              env=env, cwd=str(ROOT), timeout=120)
        assert proc.returncode == 0, proc.stderr
        report = None
        for line in proc.stdout.splitlines():
            if line.startswith("@@REPORT@@"):
                report = json.loads(line[len("@@REPORT@@"):])
        assert report is not None, proc.stdout + proc.stderr
        return report
    return _run


@pytest.fixture
def need_pull_sheet_data():
    if not (ROOT / "data" / "pull_sheet").is_dir():
        pytest.skip("data/pull_sheet/ is missing")


@pytest.fixture
def need_recipes_data():
    if not (ROOT / "data" / "recipes").is_dir():
        pytest.skip("data/recipes/ is missing")

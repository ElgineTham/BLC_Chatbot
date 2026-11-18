"""Shared fixtures for spec 036 tests (content-hash ingest, CI workflow).

Unit tests use a Chroma store in tmp_path with fake embeddings and a temp data_dir.
Nothing here touches the real data/ or .chroma/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "backend" / "scripts"), str(ROOT / "backend" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ci_helpers import X_TEXT, Y_TEXT, make_store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return make_store(tmp_path / "chroma")


@pytest.fixture
def data_dir(tmp_path):
    """Temp data dir: x.md, sub/y.md, z.json, p.jpg."""
    d = tmp_path / "data"
    (d / "sub").mkdir(parents=True)
    (d / "x.md").write_text(X_TEXT, encoding="utf-8")
    (d / "sub" / "y.md").write_text(Y_TEXT, encoding="utf-8")
    (d / "z.json").write_text('{"k": "json should be ignored"}', encoding="utf-8")
    (d / "p.jpg").write_bytes(b"\xff\xd8\xff not really a jpeg")
    return d

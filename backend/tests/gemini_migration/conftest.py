"""Shared fixtures for spec 037 tests (Gemini migration). Unit tests use fake embeddings and tmp_path only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "backend" / "scripts"), str(ROOT / "backend" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gm_helpers import X_TEXT, Y_TEXT, make_store  # noqa: E402


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
    (d / "z.json").write_text('{"k": "ignored"}', encoding="utf-8")
    (d / "p.jpg").write_bytes(b"\xff\xd8\xff not really a jpeg")
    return d


@pytest.fixture
def no_key(monkeypatch):
    """GOOGLE_API_KEY (and the library's alternative name) unset."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def live_key():
    """Real key for integration tests; loads .env from the repo root; skips when absent."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:  # pragma: no cover
        pass
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        pytest.skip("GOOGLE_API_KEY is not set")
    return key

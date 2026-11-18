"""Tests for spec 034 section 6.2 (DEPS): dependency versions and manifest / page colours."""
import re
from importlib.metadata import version

from fastapi.testclient import TestClient

from polish_helpers import REPO_ROOT
from web import ChatTurn, create_app


def _ver(text):
    return tuple(int(p) for p in re.findall(r"\d+", text)[:3])


def _deps():
    """Quoted dependency strings from pyproject.toml, e.g. 'uvicorn (>=0.54,<1.0)'."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.findall(r'"([A-Za-z0-9_.\-]+ ?\([^"\n]*\))"', text)


def _find(name):
    return [d for d in _deps() if d.strip().lower().startswith(name)]


def _fake_answerer(question, history, on_token):
    return ChatTurn(reply="x", history=history)


def test_deps1_installed_uvicorn_at_least_054():
    """Covers: AC-3 (right), DEPS-1. Installed uvicorn is >= 0.54."""
    assert _ver(version("uvicorn")) >= (0, 54)


def test_deps2_uvicorn_constraint_allows_054():
    """Covers: AC-3 (right), DEPS-2. The uvicorn constraint has a lower bound <= 0.54 and an
    upper bound above 0.54 and at most 1.0."""
    (line,) = _find("uvicorn")
    lower = re.search(r">=\s*([\d.]+)", line)
    upper = re.search(r"<\s*([\d.]+)", line)
    assert lower and upper, line
    assert _ver(lower.group(1)) <= (0, 54)
    assert (0, 54) < _ver(upper.group(1)) <= (1, 0)


def test_deps2_old_uvicorn_cap_gone():
    """Covers: AC-3 (wrong). The spec 032 cap (<0.40) is no longer present."""
    (line,) = _find("uvicorn")
    assert "<0.40" not in line.replace(" ", "")


def test_deps2_fastapi_httpx_unchanged():
    """Covers: AC-3 (boundary), DEPS-2. fastapi and httpx constraints are unchanged."""
    deps = [d.replace(" ", "") for d in _deps()]
    assert "fastapi(>=0.115,<0.120)" in deps
    assert "httpx(>=0.27,<0.29)" in deps


def test_deps3_manifest_colours():
    """Covers: AC-4 (right), DEPS-3. Manifest theme_color / background_color are the palette values."""
    r = TestClient(create_app(_fake_answerer)).get("/manifest.webmanifest")
    assert r.status_code == 200
    m = r.json()
    assert m["theme_color"].lower() == "#5e7a1f"
    assert m["background_color"].lower() == "#faf8f1"


def test_deps3_manifest_not_old_sage():
    """Covers: AC-4 (wrong). The old sage colours are gone from the manifest."""
    m = TestClient(create_app(_fake_answerer)).get("/manifest.webmanifest").json()
    assert m["theme_color"].lower() not in ("#4f7d5c", "#8fb996")
    assert m["background_color"].lower() not in ("#4f7d5c", "#8fb996")


def test_deps3_page_theme_color_meta():
    """Covers: AC-4 (right). The page's <meta name="theme-color"> is #5E7A1F."""
    html = TestClient(create_app(_fake_answerer)).get("/").text
    m = re.search(r'<meta[^>]*name=["\']theme-color["\'][^>]*>', html, re.I)
    assert m, "no theme-color meta"
    assert "#5e7a1f" in m.group(0).lower()

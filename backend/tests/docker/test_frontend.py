"""Spec 035 section 6.3: frontend uses relative API paths only (unit, no Docker)."""
import pytest

from docker_helpers import REPO_ROOT

FRONTEND = REPO_ROOT / "frontend"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".avif", ".bmp"}
FORBIDDEN = ["localhost", "127.0.0.1", "0.0.0.0", ":8000"]


def _text_files():
    return [
        p for p in sorted(FRONTEND.rglob("*"))
        if p.is_file() and p.suffix.lower() not in IMAGE_SUFFIXES
    ]


def test_frontend_has_text_files_to_check():
    """Covers: AC-12 (boundary), FRONTEND-1. The scan is not vacuous: index.html is among the files."""
    names = {p.name for p in _text_files()}
    assert "index.html" in names


@pytest.mark.parametrize("forbidden", FORBIDDEN)
def test_no_hardcoded_host_or_port(forbidden):
    """Covers: AC-12 (wrong), FRONTEND-1. No frontend text file contains the forbidden string."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _text_files()
        if forbidden in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_page_calls_api_by_relative_path():
    """Covers: AC-12 (right), FRONTEND-1. The frontend references /api/chat."""
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in _text_files())
    assert "/api/chat" in text

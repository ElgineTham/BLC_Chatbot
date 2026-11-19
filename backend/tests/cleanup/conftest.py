"""Shared fixtures for the spec 041 cleanup tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo() -> Path:
    """Repository root (backend/tests/cleanup/conftest.py -> parents[3])."""
    return Path(__file__).resolve().parents[3]

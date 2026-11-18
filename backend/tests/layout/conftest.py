"""Shared fixtures for the spec 033 layout and path tests.

REPO_ROOT is the folder that holds pyproject.toml. This file is at
<REPO_ROOT>/backend/tests/layout/conftest.py, so the repo root is parents[3].
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    assert (REPO_ROOT / "pyproject.toml").is_file(), "REPO_ROOT must hold pyproject.toml"
    return REPO_ROOT

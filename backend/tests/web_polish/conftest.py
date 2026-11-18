"""Shared fixtures for spec 034 tests. Helpers live in polish_helpers.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from polish_helpers import FakeModel  # noqa: E402


@pytest.fixture
def fake_model():
    return FakeModel(calls=[])


@pytest.fixture
def short_history():
    return [
        {"role": "user", "content": "Where is the coffee?"},
        {"role": "assistant", "content": "In the pantry."},
    ]

"""Shared fixtures for the web chat tests (spec 032).

Helper code lives in web_helpers.py; this directory is put on sys.path so test
modules can import it even under --import-mode=importlib.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web import create_app  # noqa: E402
from web_helpers import FakeAnswerer  # noqa: E402


@pytest.fixture
def fake():
    return FakeAnswerer(pieces=["The ", "coffee", " is here."], reply="The coffee is here.")


@pytest.fixture
def make_client():
    def _make(answerer):
        return TestClient(create_app(answerer))

    return _make


@pytest.fixture
def client(fake, make_client):
    return make_client(fake)

"""Helpers for the web chat tests (spec 032). Put on sys.path by conftest.py."""
import json
from pathlib import Path

from web import ChatTurn

REPO_ROOT = Path(__file__).resolve().parents[3]
LOGO_FILE = REPO_ROOT / "docs" / "specs" / "032-assets" / "blc_logo.png"


class FakeAnswerer:
    """Records calls; emits scripted tokens; returns a scripted ChatTurn or raises."""

    def __init__(self, pieces=(), reply="the reply", history=None, raises=None):
        self.pieces = list(pieces)
        self.reply = reply
        self.history = history if history is not None else [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "the reply"},
        ]
        self.raises = raises
        self.calls = []  # list of (question, history)

    def __call__(self, question, history, on_token):
        self.calls.append((question, history))
        for piece in self.pieces:
            on_token(piece)
        if self.raises is not None:
            raise self.raises
        return ChatTurn(reply=self.reply, history=self.history)


def parse_lines(response):
    """Parse an NDJSON response body into a list of dicts (one per non-empty line)."""
    return [json.loads(line) for line in response.text.split("\n") if line.strip()]


def post_raw(client, body: bytes):
    return client.post(
        "/api/chat", content=body, headers={"content-type": "application/json"}
    )

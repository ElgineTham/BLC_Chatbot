"""Plain helpers for the domain retrieval tests (spec 028). Imported via conftest, which puts this directory on sys.path."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN_GOLDEN = ROOT / "evals" / "retrieval" / "domain_golden.jsonl"
FOOD_GOLDEN = ROOT / "evals" / "retrieval" / "food_golden.jsonl"
BASE_GOLDEN = ROOT / "evals" / "retrieval" / "golden.jsonl"

SKIP_NO_DOMAIN = "Store has chunks without a domain label: wipe .chroma/ and re-run scripts/ingest.py."


def load_jsonl(path: Path) -> list[dict]:
    cases: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def ollama_running() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
            return True
    except Exception:
        return False


class FakeDoc:
    """Minimal stand-in for a LangChain Document."""

    def __init__(self, text: str = "", source: str = "x.md"):
        self.page_content = text
        self.metadata = {"source": source}


class FakeStore:
    """Records every similarity_search call; returns queued results (or [] when exhausted)."""

    def __init__(self, *results: list):
        self.calls: list[tuple[str, dict]] = []
        self._results = list(results)

    def similarity_search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self._results:
            return self._results.pop(0)
        return []


FOOD = frozenset({"food"})
BEV = frozenset({"beverage"})
BOTH = frozenset({"food", "beverage"})

LEXICON = {
    "coffee": frozenset({"beverage"}),
    "croissants": frozenset({"food"}),
    "water": frozenset({"food", "beverage"}),
    "iced tea": frozenset({"beverage"}),
}

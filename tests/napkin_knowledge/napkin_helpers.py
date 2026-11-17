"""Plain helpers for the napkin knowledge tests (spec 031). Imported via conftest, which puts this directory on sys.path."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAPKIN_SOURCE = "data/pull_sheet/rules/napkins.md"
NAPKIN_FILE = ROOT / "data" / "pull_sheet" / "rules" / "napkins.md"
NAPKIN_GOLDEN = ROOT / "evals" / "retrieval" / "napkin_golden.jsonl"

NAPKIN_MD = """# Napkins

Bay Laurel Catering uses two kinds of napkins: cocktail napkins and dinner napkins. This file says where they are kept and when to bring each kind.

## Where the napkins are
Cocktail napkins and dinner napkins are both kept on the metal rack in the pull area in the service room.

## When to bring cocktail napkins
- Bring cocktail napkins for a breakfast.
- Bring cocktail napkins for a reception.
- Bring cocktail napkins whenever any beverage is ordered.

## When to bring dinner napkins
- Bring dinner napkins for a lunch.
- Bring dinner napkins for a dinner.
- Bring dinner napkins for a plated meal.
"""

FOOD_MD = """# Food

## Breakfast
**Butter croissants**
- Served with raspberry preserves.
"""

COFFEE_MD = """# Coffee

**Coffee**
- One gallon serves 16.

**Iced tea**
- Brewed fresh, served over ice.
"""


def write_data_dir(root: Path, with_napkin: bool = True) -> Path:
    """Small data dir: a food file, a beverage file, and (optionally) the napkin file."""
    menu = root / "pull_sheet" / "menu"
    rules = root / "pull_sheet" / "rules"
    supplies = root / "supplies"
    for d in (menu, rules, supplies):
        d.mkdir(parents=True, exist_ok=True)
    (menu / "food.md").write_text(FOOD_MD, encoding="utf-8")
    (supplies / "coffee.md").write_text(COFFEE_MD, encoding="utf-8")
    if with_napkin:
        (rules / "napkins.md").write_text(NAPKIN_MD, encoding="utf-8")
    return root


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

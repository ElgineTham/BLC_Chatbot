"""Plain helpers for the food menu tests (spec 025). Imported via conftest, which puts this directory on sys.path."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOOD_SOURCE = "data/pull_sheet/menu/food.md"
FOOD_PATH = ROOT / FOOD_SOURCE
GOLDEN_PATH = ROOT / "evals" / "retrieval" / "food_golden.jsonl"

SECTION_HEADINGS = [
    "Storage locations",
    "Hot breakfast",
    "Bakery",
    "Yogurt",
    "Fruit",
    "Snacks",
    "Lunch",
    "Desserts and cookies",
    "Breakfast packages",
]


def has_heading(text: str, heading: str) -> bool:
    """A chunk has heading H when a line equals '## H'."""
    return any(line.rstrip() == f"## {heading}" for line in text.splitlines())


def h2_headings_in(text: str) -> list[str]:
    return [line.rstrip()[3:] for line in text.splitlines() if line.startswith("## ")]


def section_text(text: str, heading: str) -> str:
    """Text of food.md under '## heading' up to the next '## ' heading."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line.rstrip() == f"## {heading}"
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def bold_items(text: str) -> list[str]:
    return [m.strip() for m in re.findall(r"\*\*(.+?)\*\*", text) if m.strip()]


def load_golden() -> list[dict]:
    cases: list[dict] = []
    with GOLDEN_PATH.open(encoding="utf-8") as handle:
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

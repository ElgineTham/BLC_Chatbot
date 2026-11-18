"""Plain helpers for the food answer eval (spec 027). Imported via conftest, which puts this directory on sys.path."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = ROOT / "evals" / "answers" / "food_answers.jsonl"
FOOD_SOURCE = "data/pull_sheet/menu/food.md"
MIN_PASS_RATE = 0.90

# id, question, golden case whose reference is used, answer, expected pass
CAL_ROWS = [
    ("CAL-1", "Do I need to bring anything with croissants?", "croissant-extras",
     "Yes. Bring the raspberry preserves from the service cooler.", True),
    ("CAL-2", "Do I need to bring anything with croissants?", "croissant-extras",
     "No, you do not need to bring anything with croissants. "
     "They are on the metal rack in the service room.", False),
    ("CAL-3", "Do butter croissants come with raspberry preserves?", "croissant-preserves",
     "Yes, on a BEO they are served with raspberry preserves, which are in the service "
     "cooler and pulled with the croissants.", True),
    ("CAL-4", "Do butter croissants come with raspberry preserves?", "croissant-preserves",
     "No, they do not come with raspberry preserves. The preserves are served separately.",
     False),
    ("CAL-5", "Where are the cupcakes?", "abstain-cupcakes",
     "I don't know. The documents don't cover cupcakes.", True),
    ("CAL-6", "Where are the cupcakes?", "abstain-cupcakes",
     "Cupcakes are in the service cooler.", False),
]


def load_golden() -> list[dict]:
    assert GOLDEN_PATH.exists(), f"{GOLDEN_PATH} is missing"
    cases: list[dict] = []
    with GOLDEN_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def reference_of(case_id: str) -> str:
    for case in load_golden():
        if case["id"] == case_id:
            return case["turns"][0]["reference"]
    raise AssertionError(f"golden case {case_id!r} not found")


def cal_cases() -> list[dict]:
    return [
        {"id": cid, "question": q, "reference": reference_of(src), "answer": a, "expected": exp}
        for (cid, q, src, a, exp) in CAL_ROWS
    ]


def golden_ids() -> list[str]:
    try:
        return [c["id"] for c in load_golden()]
    except Exception:
        return []


@dataclass
class TurnResult:
    case_id: str
    turn: int  # 1-based
    question: str
    reply: str
    passed: bool
    reason: str
    must_pass: bool


def describe(results: list[TurnResult]) -> str:
    """AC-6: every listed turn with case id, turn number, question, reply and judge reason."""
    return "\n".join(
        f"- case {r.case_id}, turn {r.turn}: question={r.question!r}\n"
        f"    reply={r.reply!r}\n    judge reason={r.reason!r}"
        for r in results
    )


def failed_calibration_ids(results) -> list[str]:
    failed = []
    for case in cal_cases():
        res = results[case["id"]]
        if isinstance(res, Exception) or res.passed != case["expected"]:
            failed.append(case["id"])
    return failed


def installed_models() -> list[str] | None:
    """Model names from Ollama, or None when Ollama is not running."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return [m.get("name", "") for m in data.get("models", [])]


def has_model(installed: list[str], wanted: str) -> bool:
    names = set(installed)
    return wanted in names or (":" not in wanted and f"{wanted}:latest" in names)

"""Retrieval Hit@k eval against evals/retrieval/golden.jsonl."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
GOLDEN_PATH = ROOT / "evals" / "retrieval" / "golden.jsonl"

sys.path.insert(0, str(SCRIPTS))

from chat import CHROMA_DIR, TOP_K, build_store, retrieve  # noqa: E402


def load_golden_cases() -> list[dict]:
    cases: list[dict] = []
    with GOLDEN_PATH.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            case = json.loads(text)
            case["_line"] = line_no
            cases.append(case)
    return cases


GOLDEN_CASES = load_golden_cases()
RETRIEVAL_CASES = [c for c in GOLDEN_CASES if c.get("expected_sources")]
ABSTAIN_ONLY_CASES = [c for c in GOLDEN_CASES if not c.get("expected_sources")]


@pytest.fixture(scope="module")
def store():
    if not CHROMA_DIR.exists():
        pytest.skip(
            f"Chroma store not found at {CHROMA_DIR}. Run scripts/ingest.py first."
        )
    return build_store()


@pytest.mark.parametrize(
    "case",
    RETRIEVAL_CASES,
    ids=[c["id"] for c in RETRIEVAL_CASES],
)
def test_retrieval_hit_at_k(store, case: dict) -> None:
    """Expected source path(s) must appear in the top-k retrieved docs."""
    docs = retrieve(store, case["question"])
    retrieved_sources = [doc.metadata.get("source") for doc in docs]
    expected = case["expected_sources"]
    k = case.get("k", TOP_K)

    assert docs, f"{case['id']}: retrieval returned no documents"
    assert len(docs) <= k

    missing = [src for src in expected if src not in retrieved_sources]
    assert not missing, (
        f"{case['id']}: missing expected source(s) {missing} in top-{k}. "
        f"Retrieved: {retrieved_sources}"
    )


@pytest.mark.parametrize(
    "case",
    ABSTAIN_ONLY_CASES,
    ids=[c["id"] for c in ABSTAIN_ONLY_CASES],
)
def test_oos_cases_have_no_expected_source(case: dict) -> None:
    """Out-of-scope rows are labeled for generation/abstain checks, not Hit@k."""
    assert case["expected_sources"] == []
    assert case.get("expect_abstain") is True

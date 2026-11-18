"""RET: retrieval hit rate for food.md against the real store (spec 025 section 6.3)."""

from __future__ import annotations

import pytest

from chat import TOP_K, retrieve
from food_helpers import SECTION_HEADINGS, has_heading, load_golden

MIN_HIT_RATE = 0.90


def _headings_of(text: str) -> list[str]:
    return [h for h in SECTION_HEADINGS if has_heading(text, h)]


def _doc_matches(doc, expected_source: str, entry: dict) -> bool:
    if doc.metadata.get("source") != expected_source:
        return False
    if not has_heading(doc.page_content, entry["heading"]):
        return False
    low = doc.page_content.lower()
    return all(m.lower() in low for m in entry["must_contain"])


def case_passes(case: dict, docs: list) -> bool:
    """Every expected chunk is matched by at least one retrieved document."""
    return all(
        any(_doc_matches(d, case["expected_source"], e) for d in docs)
        for e in case["expected_chunks"]
    )


def describe_failure(case: dict, docs: list) -> str:
    lines = [f"- {case['id']}: {case['question']!r}", f"    expected: {case['expected_chunks']}"]
    for d in docs:
        low = d.page_content.lower()
        entries = []
        for e in case["expected_chunks"]:
            lacking = [m for m in e["must_contain"] if m.lower() not in low]
            entries.append(f"{e['heading']}: lacks {lacking}")
        lines.append(
            f"    retrieved {d.metadata.get('source')} headings={_headings_of(d.page_content)} "
            f"[{'; '.join(entries)}]"
        )
    return "\n".join(lines)


# ---- unit tests of the scoring logic (no Ollama) ----

class _Doc:
    def __init__(self, source: str, text: str):
        self.metadata = {"source": source}
        self.page_content = text


_CASE = {
    "id": "x",
    "question": "q",
    "expected_source": "data/pull_sheet/menu/food.md",
    "expected_chunks": [{"heading": "Bakery", "must_contain": ["Butter croissants"]}],
}


def test_scoring_passes_when_chunk_matches_case_insensitively():
    """Covers: AC-6 (right). Heading line, source and must_contain (any case) all present passes."""
    doc = _Doc(_CASE["expected_source"], "## Bakery\n- **butter CROISSANTS** in rack")
    assert case_passes(_CASE, [doc])


@pytest.mark.parametrize(
    "doc",
    [
        _Doc("data/other.md", "## Bakery\nButter croissants"),
        _Doc("data/pull_sheet/menu/food.md", "## Lunch\nButter croissants"),
        _Doc("data/pull_sheet/menu/food.md", "## Bakery\nBagels only"),
        _Doc("data/pull_sheet/menu/food.md", "Bakery heading missing\nButter croissants"),
    ],
)
def test_scoring_fails_on_wrong_source_heading_or_item(doc):
    """Covers: AC-6 (wrong). Wrong source, wrong heading, missing item or missing ## line fails."""
    assert not case_passes(_CASE, [doc])


# ---- eval ----

@pytest.mark.eval
def test_food_hit_rate(real_store):
    """Covers: AC-6, AC-7, AC-8, RET-1..RET-32 (boundary). Overall pass rate over the golden set is at least MIN_HIT_RATE; retrieve() only."""
    cases = load_golden()
    assert cases, "food_golden.jsonl is empty"
    failures: list[str] = []
    passed = 0
    for case in cases:
        docs = retrieve(real_store, case["question"])
        assert len(docs) <= TOP_K
        if case_passes(case, docs):
            passed += 1
            print(f"PASS {case['id']}")
        else:
            print(f"FAIL {case['id']}")
            failures.append(describe_failure(case, docs))
    rate = passed / len(cases)
    assert rate >= MIN_HIT_RATE, (
        f"food retrieval hit rate {rate:.2%} ({passed}/{len(cases)}) is below {MIN_HIT_RATE:.0%}. "
        "Failing cases:\n" + "\n".join(failures)
    )

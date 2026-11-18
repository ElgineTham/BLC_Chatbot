"""FILE and GOLD: the napkin data file, its ingest labels and the golden retrieval eval (spec 031 sections 6.4, 6.5)."""

from __future__ import annotations

import pytest

from chat import TOP_K
from napkin_helpers import NAPKIN_FILE, NAPKIN_GOLDEN, NAPKIN_SOURCE, FakeDoc, load_jsonl

NAPKIN_MIN_HIT_RATE = 0.90


# ---- scoring (same rule as spec 028) ----

def _src(doc) -> str:
    return doc.metadata.get("source", "")


def case_passes(case: dict, docs: list) -> bool:
    for entry in case["expected_chunks"]:
        if not any(
            _src(d) == entry["source"] and all(m.lower() in d.page_content.lower() for m in entry["must_contain"])
            for d in docs
        ):
            return False
    return not any(_src(d) in case.get("forbidden_sources", []) for d in docs)


def test_scoring_rule():
    """Covers: AC-7 (right/wrong, precondition). Scoring accepts a match and rejects missing or forbidden."""
    case = {
        "expected_chunks": [{"source": "a.md", "must_contain": ["Rack"]}],
        "forbidden_sources": ["b.md"],
    }
    assert case_passes(case, [FakeDoc("the metal RACK", "a.md")])
    assert not case_passes(case, [FakeDoc("the metal rack", "a.md"), FakeDoc("x", "b.md")])
    assert not case_passes(case, [FakeDoc("nothing", "a.md")])
    assert not case_passes(case, [])


def test_golden_file_shape():
    """Covers: AC-7 (right, precondition). 20 cases with the required keys and unique ids."""
    cases = load_jsonl(NAPKIN_GOLDEN)
    assert len(cases) == 20
    assert len({c["id"] for c in cases}) == 20
    for c in cases:
        for key in ("id", "question", "expected_chunks", "forbidden_sources", "must_pass", "notes"):
            assert key in c, f"{c.get('id')} lacks {key}"


# ---- FILE ----

@pytest.mark.integration
def test_file_locations_and_rules():
    """Covers: AC-6 (right), FILE-1. File names the metal rack, pull area, service room and all six cases."""
    low = NAPKIN_FILE.read_text(encoding="utf-8").lower()
    for phrase in ("metal rack", "pull area", "service room"):
        assert phrase in low
    for line in (
        "cocktail napkins for a breakfast",
        "cocktail napkins for a reception",
        "cocktail napkins whenever any beverage",
        "dinner napkins for a lunch",
        "dinner napkins for a dinner",
        "dinner napkins for a plated meal",
    ):
        assert line in low, line


@pytest.mark.integration
def test_file_structure_and_size():
    """Covers: AC-6 (boundary), FILE-2. Title, three sections, and small enough to be one chunk."""
    text = NAPKIN_FILE.read_text(encoding="utf-8")
    lines = [ln.rstrip() for ln in text.splitlines()]
    assert lines[0] == "# Napkins"
    for heading in (
        "## Where the napkins are",
        "## When to bring cocktail napkins",
        "## When to bring dinner napkins",
    ):
        assert heading in lines, heading
    assert len(text) // 4 < 500


# ---- GOLD ----

@pytest.mark.eval
def test_napkin_hit_rate(domain_store):
    """Covers: AC-7 (boundary), GOLD-1. napkin_golden through DomainStore scores at least 0.90."""
    cases = load_jsonl(NAPKIN_GOLDEN)
    passed, failed_ids, lines = 0, [], []
    for case in cases:
        docs = domain_store.similarity_search(case["question"], k=TOP_K)
        ok = case_passes(case, docs)
        lines.append(f"{case['id']}: {'pass' if ok else 'FAIL'} {[_src(d) for d in docs]}")
        if ok:
            passed += 1
        else:
            failed_ids.append(case["id"])
    print("\n".join(lines))
    rate = passed / len(cases)
    assert rate >= NAPKIN_MIN_HIT_RATE, (
        f"napkin hit rate {rate:.2%} ({passed}/{len(cases)}) below {NAPKIN_MIN_HIT_RATE:.0%}; "
        f"failed: {failed_ids}\n" + "\n".join(lines)
    )


@pytest.mark.eval
@pytest.mark.parametrize("question", ["Do we need to bring anything with croissants", "What to bring with croissants"])
def test_croissant_leak_cases_no_beverage_source(domain_store, question):
    """Covers: AC-8 (wrong), GOLD-2. Croissant questions still return no beverage source."""
    docs = domain_store.similarity_search(question, k=TOP_K)
    bad = [_src(d) for d in docs if "beverage" in _src(d) or _src(d).startswith("data/supplies")
           or _src(d).startswith("data/recipes")]
    assert not bad, bad


@pytest.mark.integration
def test_ingested_napkin_chunks_labelled(real_store):
    """Covers: AC-9 (right), GOLD-4. Every napkins.md chunk is domain napkin and every napkin chunk is napkins.md."""
    metas = [m or {} for m in real_store.get(include=["metadatas"]).get("metadatas") or []]
    from_file = [m for m in metas if m.get("source") == NAPKIN_SOURCE]
    napkin_domain = [m for m in metas if m.get("domain") == "napkin"]
    assert from_file, "no napkins.md chunk"
    assert napkin_domain, "no napkin-domain chunk"
    assert all(m.get("domain") == "napkin" for m in from_file)
    assert all(m.get("source") == NAPKIN_SOURCE for m in napkin_domain)

"""RET: retrieval quality through DomainStore on the real re-ingested store (spec 028 section 6.4). Eval."""

from __future__ import annotations

import pytest

from chat import TOP_K
from domain_helpers import BASE_GOLDEN, DOMAIN_GOLDEN, FOOD_GOLDEN, FakeDoc, load_jsonl

MIN_HIT_RATE = 0.85
FOOD_MIN_HIT_RATE = 0.90


# ---- scoring ----

def _src(doc) -> str:
    return doc.metadata.get("source", "")


def domain_case_missing(case: dict, docs: list) -> list[dict]:
    """Expected chunks with no matching document (source and every must_contain, case-insensitive)."""
    missing = []
    for entry in case["expected_chunks"]:
        ok = any(
            _src(d) == entry["source"]
            and all(m.lower() in d.page_content.lower() for m in entry["must_contain"])
            for d in docs
        )
        if not ok:
            missing.append(entry)
    return missing


def domain_case_forbidden(case: dict, docs: list) -> list[str]:
    return [_src(d) for d in docs if _src(d) in case.get("forbidden_sources", [])]


def domain_case_passes(case: dict, docs: list) -> bool:
    return not domain_case_missing(case, docs) and not domain_case_forbidden(case, docs)


def describe(case: dict, docs: list) -> str:
    got = [f"{_src(d)} | {d.page_content.splitlines()[0] if d.page_content.strip() else ''}" for d in docs]
    return (
        f"- {case['id']}: {case['question']!r}\n    retrieved: {got}\n"
        f"    missing: {domain_case_missing(case, docs)}\n    forbidden hit: {domain_case_forbidden(case, docs)}"
    )


def food_case_passes(case: dict, docs: list) -> bool:
    """Spec 025 rule: every expected chunk has a doc with the source, the '## heading' line and all must_contain."""
    for e in case["expected_chunks"]:
        found = False
        for d in docs:
            if _src(d) != case["expected_source"]:
                continue
            if not any(line.rstrip() == f"## {e['heading']}" for line in d.page_content.splitlines()):
                continue
            low = d.page_content.lower()
            if all(m.lower() in low for m in e["must_contain"]):
                found = True
                break
        if not found:
            return False
    return True


# ---- unit tests of the scoring logic (no Ollama) ----

_CASE = {
    "id": "t",
    "question": "q",
    "expected_chunks": [{"source": "a.md", "must_contain": ["Jam"]}],
    "forbidden_sources": ["b.md"],
}


def test_scoring_passes():
    """Covers: AC-7 (right). Matching doc (any case) and no forbidden source passes."""
    assert domain_case_passes(_CASE, [FakeDoc("raspberry JAM", "a.md")])


def test_scoring_fails_on_forbidden_or_missing():
    """Covers: AC-7 (wrong). A forbidden source or a missing chunk fails the case."""
    assert not domain_case_passes(_CASE, [FakeDoc("Jam", "a.md"), FakeDoc("x", "b.md")])
    assert not domain_case_passes(_CASE, [FakeDoc("Butter", "a.md")])
    assert not domain_case_passes(_CASE, [])


# ---- domain golden ----

def _domain_cases() -> list[dict]:
    return load_jsonl(DOMAIN_GOLDEN)


def test_domain_golden_file_shape():
    """Covers: AC-7 (right, precondition). 10 cases, required keys, exactly two must_pass."""
    cases = _domain_cases()
    assert len(cases) == 10
    for c in cases:
        for key in ("id", "question", "expected_chunks", "forbidden_sources", "must_pass", "notes"):
            assert key in c, f"{c.get('id')} lacks {key}"
    assert sum(1 for c in cases if c["must_pass"]) == 2


@pytest.mark.eval
@pytest.mark.parametrize("case_id", ["croissants-bring-we", "croissants-what-to-bring"])
def test_must_pass_croissant_cases(domain_store, case_id):
    """Covers: AC-7 (right), RET-1, RET-2. The croissant questions get the preserves chunk and no beverage rules."""
    case = next(c for c in _domain_cases() if c["id"] == case_id)
    assert case["must_pass"] is True
    docs = domain_store.similarity_search(case["question"], k=TOP_K)
    assert domain_case_passes(case, docs), describe(case, docs)


@pytest.mark.eval
@pytest.mark.parametrize(
    "case_id",
    [
        "mixed-coffee-croissants",
        "mixed-honey-syrups",
        "mixed-bagels-coffee",
        "coffee-only",
        "lemons-only",
        "syrups-only",
        "dijon-no-beverage",
        "honey-no-beverage",
    ],
)
def test_domain_case_reports(domain_store, case_id):
    """Covers: AC-7 (right), RET-3..RET-10. Individual case result; informational, the gate is the hit rate."""
    case = next(c for c in _domain_cases() if c["id"] == case_id)
    docs = domain_store.similarity_search(case["question"], k=TOP_K)
    assert len(docs) <= TOP_K
    if case["must_pass"]:
        assert domain_case_passes(case, docs), describe(case, docs)
    elif not domain_case_passes(case, docs):
        print("FAIL " + describe(case, docs))


@pytest.mark.eval
def test_domain_hit_rate(domain_store):
    """Covers: AC-7 (boundary), RET-11. Pass rate over domain_golden is at least MIN_HIT_RATE and must_pass cases pass."""
    cases = _domain_cases()
    failures, passed, must_failed = [], 0, []
    for case in cases:
        docs = domain_store.similarity_search(case["question"], k=TOP_K)
        if domain_case_passes(case, docs):
            passed += 1
        else:
            failures.append(describe(case, docs))
            if case["must_pass"]:
                must_failed.append(case["id"])
    rate = passed / len(cases)
    assert not must_failed, f"must_pass cases failed: {must_failed}\n" + "\n".join(failures)
    assert rate >= MIN_HIT_RATE, (
        f"domain hit rate {rate:.2%} ({passed}/{len(cases)}) below {MIN_HIT_RATE:.0%}. Failing cases:\n"
        + "\n".join(failures)
    )


# ---- reused golden files ----

@pytest.mark.eval
def test_food_golden_hit_rate_through_domain_store(domain_store):
    """Covers: AC-8 (boundary), RET-12. food_golden pass rate through DomainStore is at least 0.90."""
    cases = load_jsonl(FOOD_GOLDEN)
    assert cases
    failures, passed = [], 0
    for case in cases:
        docs = domain_store.similarity_search(case["question"], k=TOP_K)
        if food_case_passes(case, docs):
            passed += 1
        else:
            failures.append(f"- {case['id']}: {case['question']!r} got {[_src(d) for d in docs]}")
    rate = passed / len(cases)
    assert rate >= FOOD_MIN_HIT_RATE, (
        f"food hit rate {rate:.2%} ({passed}/{len(cases)}) below {FOOD_MIN_HIT_RATE:.0%}:\n" + "\n".join(failures)
    )


@pytest.mark.eval
def test_base_golden_all_pass_through_domain_store(domain_store):
    """Covers: AC-8 (right), RET-13. Every golden.jsonl case with expected sources finds them in the top TOP_K."""
    cases = [c for c in load_jsonl(BASE_GOLDEN) if c.get("expected_sources")]
    assert cases
    failures = []
    for case in cases:
        docs = domain_store.similarity_search(case["question"], k=case.get("k", TOP_K))
        got = [_src(d) for d in docs]
        missing = [s for s in case["expected_sources"] if s not in got]
        if missing:
            failures.append(f"- {case['id']}: missing {missing}; retrieved {got}")
    assert not failures, "golden.jsonl cases failed:\n" + "\n".join(failures)

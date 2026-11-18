"""GOLD: validity of evals/retrieval/food_golden.jsonl (spec 025 section 6.2)."""

from __future__ import annotations

from food_helpers import FOOD_SOURCE, SECTION_HEADINGS, h2_headings_in, section_text


def test_case_count_and_unique_ids(golden_cases):
    """Covers: AC-5 (right, boundary), GOLD-1. 20-30 cases and unique non-empty ids."""
    assert 20 <= len(golden_cases) <= 30
    ids = [c.get("id") for c in golden_cases]
    assert all(isinstance(i, str) and i.strip() for i in ids)
    assert len(set(ids)) == len(ids), "duplicate ids"


def test_case_fields_valid(golden_cases):
    """Covers: AC-5 (wrong), GOLD-2. Each case has question, source, and well-formed expected chunks."""
    for c in golden_cases:
        cid = c.get("id")
        assert isinstance(c.get("question"), str) and c["question"].strip(), cid
        assert c.get("expected_source") == FOOD_SOURCE, cid
        chunks = c.get("expected_chunks")
        assert isinstance(chunks, list) and len(chunks) >= 1, f"{cid}: no expected chunks"
        for ec in chunks:
            assert isinstance(ec.get("heading"), str) and ec["heading"].strip(), cid
            must = ec.get("must_contain")
            assert isinstance(must, list) and must, f"{cid}: must_contain empty"
            assert all(isinstance(m, str) and m.strip() for m in must), cid


def test_headings_exist_and_must_contain_in_section(food_text, golden_cases):
    """Covers: AC-5 (right), GOLD-3. Heading is a real ## heading and the section holds each string (case-insensitive)."""
    real = set(h2_headings_in(food_text))
    assert real == set(SECTION_HEADINGS)
    problems: list[str] = []
    for c in golden_cases:
        for ec in c["expected_chunks"]:
            if ec["heading"] not in real:
                problems.append(f"{c['id']}: unknown heading {ec['heading']!r}")
                continue
            body = section_text(food_text, ec["heading"]).lower()
            for m in ec["must_contain"]:
                if m.lower() not in body:
                    problems.append(f"{c['id']}: {m!r} not under '## {ec['heading']}'")
    assert not problems, "\n".join(problems)


def test_at_least_three_multi_chunk_cases(golden_cases):
    """Covers: AC-5 (boundary), GOLD-4. At least 3 cases expect two or more chunks."""
    multi = [c for c in golden_cases if len(c["expected_chunks"]) >= 2]
    assert len(multi) >= 3

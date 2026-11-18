"""AC-4: retrieval eval against the real store (read only)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def _phrases(chunk: str) -> list[str]:
    """Where the chunk lists phrases joined by ' or ', any one is enough."""
    return [p.strip().casefold() for p in chunk.split(" or ") if p.strip()]


def test_expected_chunk_is_retrieved(store, answer_case):
    """Covers: AC-4 (right), EC-1 (skip if not ingested), EC-2/EC-3 (cases S, A1-A3). At most TOP_K chunks are returned and at least one from the case's source contains the phrase."""
    from chat import TOP_K, retrieve

    docs = retrieve(store, answer_case["question"])
    cid = answer_case["id"]
    assert len(docs) <= TOP_K, f"{cid}: {len(docs)} chunks returned, TOP_K={TOP_K}"

    wanted = _phrases(answer_case["chunk"])
    from_source = [
        d for d in docs if d.metadata.get("source") == answer_case["source"]
    ]
    hit = any(
        phrase in d.page_content.casefold() for d in from_source for phrase in wanted
    )
    assert hit, (
        f"{cid}: no retrieved chunk from {answer_case['source']} contains any of "
        f"{wanted}. Sources retrieved: {[d.metadata.get('source') for d in docs]}"
    )


def test_retrieved_documents_have_source_metadata(store):
    """Covers: AC-4 (boundary). Every retrieved chunk carries metadata['source'] as a non-empty string."""
    from chat import retrieve

    docs = retrieve(store, "For 7 gallons of coffee, how many cambros do I need?")
    assert docs
    for d in docs:
        assert isinstance(d.metadata.get("source"), str) and d.metadata["source"]

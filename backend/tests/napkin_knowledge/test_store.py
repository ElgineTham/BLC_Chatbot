"""STORE: DomainStore with napkin questions and a fake wrapped store (spec 031 section 6.3)."""

from __future__ import annotations

from blc.retrieval import DomainStore
from napkin_helpers import FakeDoc, FakeStore


def _docs(n: int = 3) -> list[FakeDoc]:
    return [FakeDoc(f"doc {i}", f"s{i}.md") for i in range(n)]


def _filter(fake: FakeStore, index: int = 0):
    return fake.calls[index][1].get("filter")


def test_napkin_alone_filter(napkin_lexicon):
    """Covers: AC-5 (right), STORE-3. Napkin alone filters on napkin only."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=napkin_lexicon).similarity_search("Where are the napkins?", k=3)
    assert len(fake.calls) == 1
    assert _filter(fake) == {"domain": {"$in": ["napkin"]}}


def test_beverage_question_never_adds_napkin(napkin_lexicon):
    """Covers: AC-5 (wrong), STORE-4 (extra). A beverage question without napkin filters on beverage only."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=napkin_lexicon).similarity_search("Where is the coffee?", k=3)
    assert _filter(fake) == {"domain": {"$in": ["beverage"]}}


def test_empty_filtered_result_falls_back_unfiltered(napkin_lexicon):
    """Covers: AC-5 (boundary), STORE-5. Empty filtered result triggers an unfiltered second search."""
    fallback = _docs(2)
    fake = FakeStore([], list(fallback))
    out = DomainStore(fake, lexicon=napkin_lexicon).similarity_search("Where are the napkins?", k=3)
    assert len(fake.calls) == 2
    assert _filter(fake, 0) == {"domain": {"$in": ["napkin"]}}
    assert "filter" not in fake.calls[1][1]
    assert len(out) == 2 and all(a is b for a, b in zip(out, fallback))


def test_k_passed_through(napkin_lexicon):
    """Covers: AC-5 (right, extra). The requested k is passed to the wrapped search."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=napkin_lexicon).similarity_search("Where are the napkins?", k=2)
    assert fake.calls[0][1]["k"] == 2

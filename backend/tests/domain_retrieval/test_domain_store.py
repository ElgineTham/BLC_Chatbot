"""STORE: DomainStore with a fake wrapped store (spec 028 section 6.3)."""

from __future__ import annotations

from blc.retrieval import DomainStore
from domain_helpers import FakeDoc, FakeStore


def _docs(n: int = 3) -> list[FakeDoc]:
    return [FakeDoc(f"doc {i}", f"s{i}.md") for i in range(n)]


def test_food_only_filter(lexicon):
    """Covers: AC-5 (right), STORE-1. Food-only query: one call with k=3 and a food $in filter."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=lexicon).similarity_search("Where are the croissants?", k=3)
    assert len(fake.calls) == 1
    query, kwargs = fake.calls[0]
    assert query == "Where are the croissants?"
    assert kwargs == {"k": 3, "filter": {"domain": {"$in": ["food"]}}}


def test_mixed_filter_sorted(lexicon):
    """Covers: AC-5 (right), STORE-2. Food and beverage: $in list is sorted ['beverage','food']."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=lexicon).similarity_search("coffee and croissants", k=3)
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == {"k": 3, "filter": {"domain": {"$in": ["beverage", "food"]}}}


def test_multi_domain_item_filter(lexicon):
    """Covers: AC-5 (right, extra). An item in two domains filters on both."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=lexicon).similarity_search("water", k=2)
    assert fake.calls[0][1]["filter"] == {"domain": {"$in": ["beverage", "food"]}}


def test_no_known_item_has_no_filter(lexicon):
    """Covers: AC-5 (wrong), STORE-3. Unknown items: one call with k=3 and no filter argument."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=lexicon).similarity_search("Where is the flour?", k=3)
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == {"k": 3}
    assert "filter" not in fake.calls[0][1]


def test_blank_query_has_no_filter(lexicon):
    """Covers: AC-5 (boundary). A blank query is searched unfiltered."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=lexicon).similarity_search("   ", k=3)
    assert "filter" not in fake.calls[0][1]


def test_documents_returned_unchanged_in_order(lexicon):
    """Covers: AC-5 (right), STORE-4. Same documents in the same order as the wrapped store gave."""
    docs = _docs(4)
    fake = FakeStore(list(docs))
    out = DomainStore(fake, lexicon=lexicon).similarity_search("croissants", k=4)
    assert [d.page_content for d in out] == [d.page_content for d in docs]
    assert all(a is b for a, b in zip(out, docs))


def test_empty_filtered_result_retries_unfiltered(lexicon):
    """Covers: AC-6 (right), STORE-5. Empty filtered result triggers a second call without filter; its result is returned."""
    fallback = _docs(2)
    fake = FakeStore([], fallback)
    out = DomainStore(fake, lexicon=lexicon).similarity_search("croissants", k=3)
    assert len(fake.calls) == 2
    assert "filter" in fake.calls[0][1]
    assert "filter" not in fake.calls[1][1]
    assert fake.calls[1][1]["k"] == 3
    assert fake.calls[1][0] == "croissants"
    assert out == fallback


def test_nonempty_filtered_result_no_second_call(lexicon):
    """Covers: AC-6 (wrong), STORE-6. A non-empty filtered result means no second call."""
    fake = FakeStore(_docs(1))
    DomainStore(fake, lexicon=lexicon).similarity_search("croissants", k=3)
    assert len(fake.calls) == 1


def test_unfiltered_empty_is_not_retried(lexicon):
    """Covers: AC-6 (boundary, extra). When no filter was used and the result is empty, the store is not called again."""
    fake = FakeStore([])
    out = DomainStore(fake, lexicon=lexicon).similarity_search("flour", k=3)
    assert len(fake.calls) == 1
    assert list(out) == []


def test_custom_lexicon_is_used(lexicon):
    """Covers: AC-5 (right), STORE-7. A custom lexicon decides the filter, not the real one."""
    fake = FakeStore(_docs())
    custom = {"zorp": frozenset({"beverage"})}
    DomainStore(fake, lexicon=custom).similarity_search("Where is the zorp?", k=3)
    assert fake.calls[0][1]["filter"] == {"domain": {"$in": ["beverage"]}}
    fake2 = FakeStore(_docs())
    DomainStore(fake2, lexicon=custom).similarity_search("croissants", k=3)
    assert "filter" not in fake2.calls[0][1]


def test_default_k_is_four(lexicon):
    """Covers: AC-5 (boundary), STORE-8. Without k the wrapped store receives k=4."""
    fake = FakeStore(_docs())
    DomainStore(fake, lexicon=lexicon).similarity_search("croissants")
    assert fake.calls[0][1]["k"] == 4

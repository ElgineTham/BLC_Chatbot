"""A store wrapper that searches only the domains a question is about."""

from __future__ import annotations

from langchain_core.documents import Document

from blc.retrieval.detect import detect_domains
from blc.retrieval.lexicon import Lexicon, load_lexicon

DEFAULT_K = 4


class DomainStore:
    def __init__(self, store, lexicon: Lexicon | None = None) -> None:
        self._store = store
        self._lexicon = load_lexicon() if lexicon is None else lexicon

    def similarity_search(self, query: str, k: int = DEFAULT_K) -> list[Document]:
        domains = detect_domains(query, self._lexicon)
        if not domains:
            return self._store.similarity_search(query, k=k)
        domain_filter = {"domain": {"$in": sorted(domains)}}
        documents = self._store.similarity_search(query, k=k, filter=domain_filter)
        if documents:
            return documents
        return self._store.similarity_search(query, k=k)

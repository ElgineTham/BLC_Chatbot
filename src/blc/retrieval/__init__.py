"""Domain-filtered retrieval (spec 028)."""

from __future__ import annotations

from blc.retrieval.detect import detect_domains
from blc.retrieval.domains import DOMAINS, OTHER_DOMAIN, domain_for
from blc.retrieval.lexicon import DATA_DIR, Lexicon, load_lexicon
from blc.retrieval.store import DomainStore

__all__ = [
    "DATA_DIR",
    "DOMAINS",
    "OTHER_DOMAIN",
    "DomainStore",
    "Lexicon",
    "detect_domains",
    "domain_for",
    "load_lexicon",
]

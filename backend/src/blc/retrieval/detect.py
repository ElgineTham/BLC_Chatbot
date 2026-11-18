"""Find which domains a question is about from the item names it contains."""

from __future__ import annotations

import re

from blc.retrieval.lexicon import Lexicon

WORD = re.compile(r"[a-z0-9]+")


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text: str) -> tuple[str, ...]:
    return tuple(_singular(word) for word in WORD.findall(text.lower()))


def _contains(words: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    size = len(phrase)
    if size == 0 or size > len(words):
        return False
    return any(words[i : i + size] == phrase for i in range(len(words) - size + 1))


def detect_domains(question: str, lexicon: Lexicon) -> frozenset[str]:
    words = _words(question or "")
    found: set[str] = set()
    for name, domains in lexicon.items():
        if _contains(words, _words(name)):
            found |= domains
    return frozenset(found)

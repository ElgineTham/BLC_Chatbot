"""DETECT: which questions search the napkin domain (spec 031 section 6.2)."""

from __future__ import annotations

import pytest

from blc.retrieval import detect_domains


def test_napkins_alone(napkin_lexicon):
    """Covers: AC-4 (right), DETECT-1. A napkin-only question gives {napkin}."""
    assert detect_domains("Where are the napkins?", napkin_lexicon) == frozenset({"napkin"})


@pytest.mark.parametrize("question", ["NAPKINS?", "Cocktail Napkin", "dinner napkins"])
def test_napkin_word_any_case_or_number(napkin_lexicon, question):
    """Covers: AC-4 (boundary), DETECT-5. Napkin or napkins in any case and with punctuation is detected."""
    assert "napkin" in detect_domains(question, napkin_lexicon)


def test_no_napkin_file_no_napkin_domain(no_napkin_lexicon):
    """Covers: AC-3 (wrong), DETECT-6. Without the napkin file, a napkin question detects nothing."""
    assert detect_domains("Where are the napkins?", no_napkin_lexicon) == frozenset()


@pytest.mark.parametrize("question", ["napkinsful", "Where are the pins?"])
def test_non_napkin_words_not_detected(napkin_lexicon, question):
    """Covers: AC-3/AC-4 (wrong/boundary), DETECT-7. Words that merely resemble napkin do not trigger it."""
    assert "napkin" not in detect_domains(question, napkin_lexicon)


def test_blank_question_detects_nothing(napkin_lexicon):
    """Covers: AC-4 (boundary, extra). A blank question gives the empty set."""
    assert detect_domains("   ", napkin_lexicon) == frozenset()
    assert detect_domains("", napkin_lexicon) == frozenset()

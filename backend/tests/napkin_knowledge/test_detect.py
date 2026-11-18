"""DETECT: which questions search the napkin domain (spec 031 section 6.2)."""

from __future__ import annotations

import pytest

from blc.retrieval import detect_domains


def test_napkins_alone(napkin_lexicon):
    """Covers: AC-4 (right), DETECT-1. A napkin-only question gives {napkin}."""
    assert detect_domains("Where are the napkins?", napkin_lexicon) == frozenset({"napkin"})


def test_napkins_with_beverage(napkin_lexicon):
    """Covers: AC-4 (right), DETECT-2. Napkin plus a beverage name gives both domains."""
    got = detect_domains("Do I need napkins for the iced tea?", napkin_lexicon)
    assert got == frozenset({"napkin", "beverage"})


def test_napkin_with_food(napkin_lexicon):
    """Covers: AC-4 (right), DETECT-3. Napkin plus a food name gives both domains."""
    got = detect_domains("Which napkin do I bring with the croissants?", napkin_lexicon)
    assert got == frozenset({"napkin", "food"})


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Where are the croissants?", frozenset({"food"})),
        ("What to bring with croissants", frozenset({"food"})),
        ("Where is the coffee?", frozenset({"beverage"})),
    ],
)
def test_no_napkin_word_no_napkin_domain(napkin_lexicon, question, expected):
    """Covers: AC-4 (wrong), DETECT-4. Without the word napkin the napkin domain is never added."""
    got = detect_domains(question, napkin_lexicon)
    assert got == expected
    assert "napkin" not in got


@pytest.mark.parametrize("question", ["NAPKINS?", "Cocktail Napkin", "dinner napkins"])
def test_napkin_word_any_case_or_number(napkin_lexicon, question):
    """Covers: AC-4 (boundary), DETECT-5. Napkin or napkins in any case and with punctuation is detected."""
    assert "napkin" in detect_domains(question, napkin_lexicon)


def test_no_napkin_file_no_napkin_domain(no_napkin_lexicon):
    """Covers: AC-3 (wrong), DETECT-6. Without the napkin file, a napkin question detects nothing."""
    assert detect_domains("Where are the napkins?", no_napkin_lexicon) == frozenset()


def test_no_napkin_file_food_and_beverage_unchanged(no_napkin_lexicon):
    """Covers: AC-3 (right), DETECT-6. Food and beverage detection work without the napkin file."""
    assert detect_domains("Where are the croissants?", no_napkin_lexicon) == frozenset({"food"})
    assert detect_domains("Where is the coffee?", no_napkin_lexicon) == frozenset({"beverage"})


def test_no_napkin_file_with_food_gives_food_only(no_napkin_lexicon):
    """Covers: AC-3 (wrong), DETECT-6 (extra). Without the file, napkin plus croissants gives only food."""
    got = detect_domains("Napkins for the croissants?", no_napkin_lexicon)
    assert got == frozenset({"food"})


@pytest.mark.parametrize("question", ["napkinsful", "Where are the pins?"])
def test_non_napkin_words_not_detected(napkin_lexicon, question):
    """Covers: AC-3/AC-4 (wrong/boundary), DETECT-7. Words that merely resemble napkin do not trigger it."""
    assert "napkin" not in detect_domains(question, napkin_lexicon)


def test_blank_question_detects_nothing(napkin_lexicon):
    """Covers: AC-4 (boundary, extra). A blank question gives the empty set."""
    assert detect_domains("   ", napkin_lexicon) == frozenset()
    assert detect_domains("", napkin_lexicon) == frozenset()

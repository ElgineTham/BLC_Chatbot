"""DET: detect_domains with a custom and the real lexicon (spec 028 section 6.2)."""

from __future__ import annotations

import pytest

from blc.retrieval import detect_domains
from domain_helpers import BEV, BOTH, FOOD


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Where are the croissants?", FOOD),
        ("I need coffee and croissants", BOTH),
        ("WHERE IS THE COFFEE", BEV),
        ("Do we need a croissant?", FOOD),
        ("Where is the water?", BOTH),
        ("Where is the iced tea?", BEV),
    ],
)
def test_custom_lexicon_matches(lexicon, question, expected):
    """Covers: AC-3 (right), DET-1..DET-6. Whole words/phrases, any case, singular or plural."""
    assert detect_domains(question, lexicon) == expected


def test_result_is_frozenset(lexicon):
    """Covers: AC-3 (right). Return type is a frozenset of domain names."""
    assert isinstance(detect_domains("coffee", lexicon), frozenset)


def test_phrase_needs_whole_phrase(lexicon):
    """Covers: AC-3 (wrong), DET-6. 'tea' alone does not match the 'iced tea' item."""
    assert detect_domains("Where is the tea?", lexicon) == frozenset()


def test_partial_word_does_not_match(lexicon):
    """Covers: AC-3 (wrong), DET-7. 'coffeehouse' does not match 'coffee'."""
    assert detect_domains("Is there a coffeehouse nearby?", lexicon) == frozenset()


@pytest.mark.parametrize("question", ["Where is the flour?", "", "   ", "\n\t"])
def test_unknown_or_blank_gives_empty(lexicon, question):
    """Covers: AC-3 (boundary), DET-8. Unknown item, empty or blank input gives empty set, no error."""
    assert detect_domains(question, lexicon) == frozenset()


def test_non_item_words_add_nothing(lexicon):
    """Covers: AC-3 (wrong). Words like 'bring' and 'where' are not items."""
    assert detect_domains("Where do we bring anything", lexicon) == frozenset()


def test_empty_lexicon_gives_empty():
    """Covers: AC-3 (boundary). An empty lexicon never matches."""
    assert detect_domains("coffee and croissants", {}) == frozenset()


def test_plural_form_in_question_matches_singular_item():
    """Covers: AC-3 (right, extra). A plural in the question matches a singular lexicon name."""
    lex = {"coffee": frozenset({"beverage"})}
    assert detect_domains("How many coffees?", lex) == BEV


def test_punctuation_does_not_block_match(lexicon):
    """Covers: AC-3 (boundary, extra). Surrounding punctuation does not stop a whole-word match."""
    assert detect_domains("(coffee), croissants!", lexicon) == BOTH


# ---- real lexicon ----

def test_real_croissants_bring(real_lexicon):
    """Covers: AC-4 (right), DET-9. 'bring' adds nothing; only food."""
    assert detect_domains("Do we need to bring anything with croissants", real_lexicon) == FOOD


def test_real_dijon(real_lexicon):
    """Covers: AC-4 (right), DET-10. Dijon mustard is food."""
    assert detect_domains("Where is the Dijon mustard?", real_lexicon) == FOOD


@pytest.mark.parametrize("question", ["Where is the coffee?", "Where is the iced tea?"])
def test_real_beverage_items(real_lexicon, question):
    """Covers: AC-4 (right), DET-11. Beverage items give only beverage."""
    assert detect_domains(question, real_lexicon) == BEV


def test_real_mixed(real_lexicon):
    """Covers: AC-4 (right), DET-12. Coffee plus croissants gives both domains."""
    assert detect_domains("Where are the coffee and the croissants?", real_lexicon) == BOTH


def test_real_bottled_water_includes_food(real_lexicon):
    """Covers: AC-4 (right), DET-13. Bottled water includes food."""
    assert "food" in detect_domains("Where is the bottled water?", real_lexicon)


def test_real_unknown_item(real_lexicon):
    """Covers: AC-4 (wrong), DET-14. Flour is unknown: empty set."""
    assert detect_domains("Where is the flour?", real_lexicon) == frozenset()


def test_load_lexicon_from_temp_dir(tmp_path):
    """Covers: AC-4 (boundary, extra). load_lexicon on an empty data dir returns an empty mapping without error."""
    from blc.retrieval import load_lexicon

    assert len(load_lexicon(tmp_path)) == 0

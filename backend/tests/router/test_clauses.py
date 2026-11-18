"""Spec 013 AC-1: split_clauses, is_follow_up, quick_label (section 4.1 to 4.3, EC-1 to EC-13).

Pure functions: no model, no Ollama, no network, nothing read under data/ (NFR-2).
"""

from __future__ import annotations

import pytest

from blc.router import (
    PULL_SHEET_ITEMS,
    QUESTION_STARTERS,
    is_follow_up,
    quick_label,
    split_clauses,
)

# ---------------------------------------------------------------- split_clauses

SPLIT_ROWS = [
    ("Where is the coffee?", ("Where is the coffee?",)),
    (
        "Where is the coffee, and how many gallons of coffee do I need for 75 people?",
        ("Where is the coffee", "how many gallons of coffee do I need for 75 people?"),
    ),
    (
        "How do I clean a cambro? How many cambros for 8 gallons of iced tea?",
        ("How do I clean a cambro?", "How many cambros for 8 gallons of iced tea?"),
    ),
    (
        "What flavors of syrup do we have; do I bring sugar for hot water for 30 guests?",
        ("What flavors of syrup do we have", "do I bring sugar for hot water for 30 guests?"),
    ),
    (
        "I need 5 gallons of coffee and lemonade. How many cambros?",
        ("I need 5 gallons of coffee and lemonade. How many cambros?",),
    ),
    (
        "I need 9 gallons of decaf and hot water, how many containers?",
        ("I need 9 gallons of decaf and hot water, how many containers?",),
    ),
    ("How many cambros for coffee and lemonade?", ("How many cambros for coffee and lemonade?",)),
    (
        "What is the recipe for iced tea for 120 people, and how much do I need?",
        ("What is the recipe for iced tea for 120 people", "how much do I need?"),
    ),
    ("", ()),
]


@pytest.mark.parametrize("question,expected", SPLIT_ROWS)
def test_split_table_rows(question, expected):
    """Covers: AC-1 (right, wrong), EC-1. Every row of the section 4.1 table gives exactly the listed parts."""
    out = split_clauses(question)
    assert isinstance(out, tuple)
    assert out == expected


@pytest.mark.parametrize("question", ["", " ", "   ", "\n", "\t \n"])
def test_split_blank_gives_empty_tuple(question):
    """Covers: AC-1 (boundary), EC-1. Blank text gives ()."""
    assert split_clauses(question) == ()


@pytest.mark.parametrize("question", ["What is this?", "What is this? ", "  What is this?  ", "Where is the coffee??"])
def test_split_question_mark_at_end_is_not_a_boundary(question):
    """Covers: AC-1 (boundary), EC-2. A question mark at the very end (or followed only by spaces) does not split."""
    out = split_clauses(question)
    assert len(out) == 1
    assert out[0] == out[0].strip()
    assert out[0].startswith(("What is this?", "Where is the coffee?"))


def test_split_question_mark_then_statement_splits_without_starter_check():
    """Covers: AC-1 (right), EC-1. Rule 1 (question mark, space, more text) splits even when the next text is not a question."""
    assert split_clauses("Where is the coffee? Thanks") == ("Where is the coffee?", "Thanks")


def test_split_several_boundaries_in_order():
    """Covers: AC-1 (right), EC-3. Several boundaries give several parts, in question order."""
    q = "Where is the coffee? Where is the tea? Where is the sugar?"
    assert split_clauses(q) == ("Where is the coffee?", "Where is the tea?", "Where is the sugar?")


def test_split_mixed_boundary_kinds_in_order():
    """Covers: AC-1 (right), EC-3. A semicolon, a question mark and an 'and how' boundary in one question."""
    q = "What is the syrup; where is the tea? How many cups for 5 guests and how many cambros for 6 gallons?"
    out = split_clauses(q)
    assert out == (
        "What is the syrup",
        "where is the tea?",
        "How many cups for 5 guests",
        "how many cambros for 6 gallons?",
    )


def test_split_extra_spaces_and_newlines_are_stripped():
    """Covers: AC-1 (boundary), EC-4. Extra spaces and newlines around the parts are stripped."""
    out = split_clauses("  Where is the coffee?   \n  How many cups?  \n")
    assert out == ("Where is the coffee?", "How many cups?")


def test_split_repeated_semicolons_leave_no_empty_or_unstripped_part():
    """Covers: AC-1 (boundary), EC-4. Repeated punctuation never leaves an empty part or a part with a leading or trailing comma or semicolon."""
    out = split_clauses("What is the sugar;; where is the tea?")
    assert out
    assert all(p and p == p.strip() and not p.startswith((",", ";")) and not p.endswith((",", ";")) for p in out)
    assert out[0] == "What is the sugar"
    assert out[-1] == "where is the tea?"


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Where is the coffee?;", ("Where is the coffee?",)),
        (";; Where is the tea?", ("Where is the tea?",)),
        ("Where is the tea;;; where is the sugar?", ("Where is the tea", "where is the sugar?")),
        ("What is the syrup; ; where is the tea?", ("What is the syrup", "where is the tea?")),
        ("Where is the tea; , ; where is the sugar?", ("Where is the tea", "where is the sugar?")),
    ],
)
def test_split_empty_pieces_are_dropped(question, expected):
    """Covers: AC-1 (boundary), EC-4, section 4.1. A piece that is empty after stripping (and removing a leading and/also) is dropped."""
    assert split_clauses(question) == expected


@pytest.mark.parametrize("question", ["; and", ";also;", "and; also"])
def test_split_pieces_empty_after_removing_leading_connector_are_dropped(question):
    """Covers: AC-1 (boundary), EC-4, EC-7. A piece that is only 'and'/'also' is empty after removal and is dropped; no empty strings are returned."""
    out = split_clauses(question)
    assert isinstance(out, tuple)
    assert all(p.strip() for p in out)


def test_split_and_needs_a_question_on_the_left():
    """Covers: AC-1 (wrong), section 4.1 rule 3. A statement on the left keeps 'and how' attached; the same words after a question split."""
    stmt = "I need coffee, and how many cups for 5 guests?"
    assert split_clauses(stmt) == (stmt,)
    assert len(split_clauses("Where is coffee, and how many cups for 5 guests?")) == 2


def test_split_comma_before_and_is_stripped():
    """Covers: AC-1 (right), EC-4. The comma before 'and' is not kept on the left part."""
    out = split_clauses("Where is the tea, and where is the sugar?")
    assert out == ("Where is the tea", "where is the sugar?")


@pytest.mark.parametrize("question,_expected", SPLIT_ROWS)
def test_split_every_part_occurs_inside_the_question(question, _expected):
    """Covers: AC-1 (right), EC-5. Every part is a piece of the user's own words (a substring of the question)."""
    for part in split_clauses(question):
        assert part in question


@pytest.mark.parametrize(
    "question",
    [
        "Where is the coffee? Where is the tea; how many cups for 5 guests and also how many cambros?",
        "What is the syrup, also how many cups do I need for 5 guests?",
        "  Where   is  the coffee ?   And where is the tea?  ",
    ],
)
def test_split_parts_are_substrings_after_boundaries(question):
    """Covers: AC-1 (boundary), EC-5. Parts are substrings even with 'also', 'and also' and odd spacing."""
    parts = split_clauses(question)
    assert parts
    for part in parts:
        assert part in question


def test_split_uppercase_and_and_how_count_as_the_words():
    """Covers: AC-1 (right), EC-6. AND and HOW are recognised ignoring case."""
    out = split_clauses("WHERE IS THE COFFEE, AND HOW MANY CUPS DO I NEED FOR 55 GUESTS?")
    assert out == ("WHERE IS THE COFFEE", "HOW MANY CUPS DO I NEED FOR 55 GUESTS?")


def test_split_mixed_case_starters():
    """Covers: AC-1 (right), EC-6. Mixed case on both sides still splits."""
    out = split_clauses("wHeRe is the coffee And hOw many cups do I need for 55 guests?")
    assert len(out) == 2
    assert out[1].lower().startswith("how many cups")


def test_split_and_also_with_and_without_comma():
    """Covers: AC-1 (right), section 4.1. 'and also' and ', also' split when both sides are questions; the connector is dropped."""
    assert split_clauses("Where is the coffee and also how many cups for 5 guests?") == (
        "Where is the coffee",
        "how many cups for 5 guests?",
    )
    assert split_clauses("Where is the coffee, and also how many cups for 5 guests?") == (
        "Where is the coffee",
        "how many cups for 5 guests?",
    )
    assert split_clauses("Where is the coffee, also how many cups for 5 guests?") == (
        "Where is the coffee",
        "how many cups for 5 guests?",
    )


def test_split_semicolon_always_splits():
    """Covers: AC-1 (right), section 4.1 rule 2. A semicolon splits even between two statements."""
    assert split_clauses("I need coffee; I need tea") == ("I need coffee", "I need tea")


@pytest.mark.parametrize(
    "question",
    [
        "Tell me where the coffee is and how many cups I need?",  # left side is a statement
        "Where is the coffee and tea?",  # right side does not start with a starter
        "Where is the coffee and lemonade?",
        "How many cups for coffee and also lemonade?",
    ],
)
def test_split_and_does_not_split_when_a_side_is_not_a_question(question):
    """Covers: AC-1 (wrong), section 4.1 rule 3. 'and' needs a starter on the right and a question on the left."""
    assert split_clauses(question) == (question,)


@pytest.mark.parametrize("question", ["Great! How many cups?", "Thanks. Where is the coffee?"])
def test_split_full_stop_and_bang_are_never_boundaries(question):
    """Covers: AC-1 (wrong), section 4.1. A statement before a question stays attached."""
    assert split_clauses(question) == (question,)


@pytest.mark.parametrize(
    "question",
    ["?", "??", "? ?", ";", ";;;", ",", "and", "and how", "also", "\n\n", "?" * 50, "How?", "a" * 5000, "ünïcode? é"],
)
def test_split_odd_input_never_raises(question):
    """Covers: AC-1 (boundary), EC-7. Odd input never raises and returns a tuple of stripped strings."""
    out = split_clauses(question)
    assert isinstance(out, tuple)
    for part in out:
        assert isinstance(part, str) and part == part.strip()


def test_question_starters_contract():
    """Covers: AC-1 (right), section 3.1. QUESTION_STARTERS holds the listed lower case words."""
    for word in ("how", "what", "where", "which", "when", "who", "why", "do", "does", "is", "are", "can", "will", "may"):
        assert word in QUESTION_STARTERS
    assert all(w == w.lower() for w in QUESTION_STARTERS)


# ---------------------------------------------------------------- is_follow_up

H_CAMBROS = [
    {"role": "user", "content": "How many cambros do I need for hot water and decaf?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]


@pytest.mark.parametrize(
    "history,question,expected",
    [
        ([], "5 gallons each.", False),
        (H_CAMBROS, "4 gallons each.", True),
        (H_CAMBROS, "85 guests.", True),
        (H_CAMBROS, "And for the orange juice?", True),
        (H_CAMBROS, "What about 6 gallons?", True),
        (H_CAMBROS, "How many hot cups do I need for 130 guests?", False),
        (H_CAMBROS, "I need 9 gallons of decaf. How many cambros?", False),
        ([{"role": "assistant", "content": "How many guests?"}], "85 guests.", False),
    ],
)
def test_follow_up_table_rows(history, question, expected):
    """Covers: AC-1 (right, wrong), EC-8. Every row of the section 4.2 table."""
    assert is_follow_up(history, question) is expected


@pytest.mark.parametrize(
    "question",
    ["Also 5 gallons.", "so 20 guests", "Then 40 guests please", "how about 85 guests?", "HOW ABOUT 85 GUESTS?", "WHAT ABOUT 6 GALLONS?"],
)
def test_follow_up_leading_words_and_about_phrases(question):
    """Covers: AC-1 (right), EC-8. A leading also/so/then is ignored, and 'what about' / 'how about' always mark a follow-up (any case)."""
    assert is_follow_up(H_CAMBROS, question) is True


def test_follow_up_then_what_about():
    """Covers: AC-1 (boundary), EC-8. 'then what about ...' counts: the leading word is ignored before the 'what about' check."""
    assert is_follow_up(H_CAMBROS, "Then what about 6 gallons?") is True


@pytest.mark.parametrize("question", ["And how many cups?", "Where is the sugar?", "Do I bring sugar?", "75 guests, what else"])
def test_follow_up_false_when_a_starter_word_is_present(question):
    """Covers: AC-1 (wrong), EC-8. A whole starter word in the question (after a leading and/also/so/then) means it is not a follow-up."""
    assert is_follow_up(H_CAMBROS, question) is False


def test_follow_up_starter_must_be_a_whole_word():
    """Covers: AC-1 (boundary), EC-8. 'shower' and 'window' contain 'how' / 'do' only inside a word, so they are not starters."""
    assert is_follow_up(H_CAMBROS, "75 guests, shower please") is True
    assert is_follow_up(H_CAMBROS, "85 guests by the window") is True


@pytest.mark.parametrize(
    "history",
    [
        [{"role": "user", "content": ""}],
        [{"role": "user", "content": "   \n"}],
        [{"role": "user", "content": None}],
        [{"content": "How many cups?"}],
        [{"role": "user"}],
        [{"role": "summary", "content": "The user asked about cups."}],
        [{"role": "assistant", "content": "Hi"}, {"role": "summary", "content": "older talk"}],
    ],
)
def test_follow_up_false_without_a_usable_user_item(history):
    """Covers: AC-1 (wrong, boundary), EC-9. Blank, missing, None or non-user items (including summary items) give False and never raise."""
    assert is_follow_up(history, "85 guests.") is False


def test_follow_up_odd_history_items_never_raise():
    """Covers: AC-1 (boundary), EC-9. Items with non-text content, no role, or a mix of bad and good items never raise."""
    odd = [{"role": "user", "content": 5}, {"content": ["x"]}, {}, {"role": None, "content": None}]
    assert isinstance(is_follow_up(odd, "85 guests."), bool)
    assert is_follow_up(odd + H_CAMBROS, "85 guests.") is True


def test_follow_up_one_good_user_item_among_bad_ones():
    """Covers: AC-1 (right), EC-9. One real user item is enough, wherever it is."""
    history = [{"role": "user", "content": None}, {"role": "user", "content": "How many cups?"}, {"role": "user", "content": ""}]
    assert is_follow_up(history, "85 guests.") is True


# ---------------------------------------------------------------- quick_label


@pytest.mark.parametrize("text", ["Where is the coffee?", "What syrup flavors do we have?", "Thanks!"])
def test_quick_label_docs_rows(text):
    """Covers: AC-1 (right), EC-10. Rows of section 4.3 that skip the model."""
    assert quick_label(text) == "DOCS"


@pytest.mark.parametrize(
    "text",
    [
        "How many cups do I need for the iced water?",
        "What do I need to bring?",
        "When does setup start for the 6 pm event?",
    ],
)
def test_quick_label_none_rows(text):
    """Covers: AC-1 (wrong), EC-10. Rows of section 4.3 that need the model."""
    assert quick_label(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Where is table 5?",
        "Where is the 2.5 gallon thing?",
        "Where is box 1,000?",
        "Where are the seven boxes?",
        "Where are the twenty-five boxes?",
        "Where are the twenty five boxes?",
        "Where are the one hundred boxes?",
        "Where is the zero waste bin?",
        "Where are the SEVEN boxes?",
        "Where is the 50-guest sign?",
    ],
)
def test_quick_label_numbers_stop_the_shortcut(text):
    """Covers: AC-1 (wrong), EC-11. Digits and spelled numbers from zero to one hundred give None."""
    assert quick_label(text) is None


def test_quick_label_number_must_be_a_whole_word():
    """Covers: AC-1 (boundary), EC-11. 'ten' inside 'often' is not a number, so the shortcut still applies."""
    assert quick_label("How often is it cleaned?") == "DOCS"


def _all_item_words():
    return sorted({w for words in PULL_SHEET_ITEMS.values() for w in words})


@pytest.mark.parametrize("word", _all_item_words())
def test_quick_label_every_item_word_stops_the_shortcut(word):
    """Covers: AC-1 (wrong), EC-12. Every word of every pull sheet item makes quick_label return None, in any case."""
    assert quick_label(f"Where is the {word}?") is None
    assert quick_label(f"WHERE IS THE {word.upper()}?") is None


def test_quick_label_item_words_are_whole_words():
    """Covers: AC-1 (boundary), EC-12. 'lemonade' is not 'lemons' and 'cupboard' is not 'cups' (spec 007), so these skip the model."""
    assert quick_label("Where is the lemonade?") == "DOCS"
    assert quick_label("Where is the cupboard?") == "DOCS"


@pytest.mark.parametrize("text", ["", " ", "\n", "  \t "])
def test_quick_label_blank_is_docs(text):
    """Covers: AC-1 (boundary), EC-13. Blank text gives 'DOCS'."""
    assert quick_label(text) == "DOCS"

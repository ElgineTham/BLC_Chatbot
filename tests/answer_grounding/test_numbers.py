"""Spec 017 AC-1: `ungrounded_numbers` (section 4.1, EC-1 to EC-6, NFR-5). Unit; pure; no model, no files."""

from __future__ import annotations

import pytest

from blc.judge import ungrounded_numbers

CAMBRO_SRC = ["Decaf: 9 gal.\n5 gal cambro: 2 (for Decaf)."]


# ---- EC-1: every row of the section 4.1 table -------------------------------

@pytest.mark.parametrize(
    "answer, sources, expected",
    [
        ("You need two 5 gal cambros.", CAMBRO_SRC, ()),
        ("You need 3 cambros for 9 gallons.", CAMBRO_SRC, ("3",)),
        ("Use 77 oz of concentrate and fill to 11 gallons.", ["Lemon concentrate: 77 oz\nWater: fill to 11 gallons"], ()),
        ("1. Pour it.\n2. Stir.\nMake 1 batch.", [""], ()),
        ("About 25 guests per gallon.", ["Coffee: 5 gal from 120 guests."], ("25",)),
        ("Bring 1,000 cups.", ["1000 cups"], ()),
        ("See data/supplies/coffee.md.", [""], ()),
    ],
)
def test_section_4_1_table(answer, sources, expected):
    """Covers: AC-1 (right/wrong), EC-1. Each row of the section 4.1 table gives its listed result."""
    assert ungrounded_numbers(answer, sources) == expected


def test_returns_a_tuple():
    """Covers: AC-1 (right). The result is a tuple, also when empty."""
    assert isinstance(ungrounded_numbers("Make 3 cups.", [""]), tuple)
    assert isinstance(ungrounded_numbers("Nothing here.", [""]), tuple)


# ---- what counts as a number -------------------------------------------------

def test_number_words_two_to_twenty_are_numbers():
    """Covers: AC-1 (right/boundary). `two` (lowest) and `twenty` (highest) count as numbers and are returned as written."""
    assert ungrounded_numbers("two and twenty", [""]) == ("two", "twenty")


@pytest.mark.parametrize("word", ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                                  "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                                  "seventeen", "eighteen", "nineteen", "twenty"])
def test_every_number_word_is_recognised(word):
    """Covers: AC-1 (right), EC-6 (boundary). Each word from two to twenty is a number, so it is ungrounded against empty sources."""
    assert ungrounded_numbers(f"Bring {word} trays.", [""]) == (word,)


def test_number_words_any_case():
    """Covers: AC-1 (right). Words match in any case and are returned as written (`Two` is 2)."""
    assert ungrounded_numbers("Two cups, TWELVE trays", [""]) == ("Two", "TWELVE")


@pytest.mark.parametrize("answer", ["one cup", "thirty cups", "a hundred cups", "Hundred"])
def test_words_outside_two_to_twenty_are_not_numbers(answer):
    """Covers: AC-1 (wrong), EC-6 (wrong). `one`, `thirty`, `hundred` are not numbers."""
    assert ungrounded_numbers(answer, [""]) == ()


@pytest.mark.parametrize("answer", ["That is often done.", "The tenant left.", "Pay attention.", "Fivefold plan", "Stone"])
def test_number_words_must_be_whole_words(answer):
    """Covers: AC-1 (wrong), EC-6 (boundary). A number word inside a longer word (often, tenant) is not a number."""
    assert ungrounded_numbers(answer, [""]) == ()


def test_decimal_numbers_returned_as_written():
    """Covers: AC-1 (right). A decimal is one number and is returned as written."""
    assert ungrounded_numbers("Add 17.5 oz.", [""]) == ("17.5",)


def test_thousands_commas_form_one_number():
    """Covers: AC-1 (right/boundary). `1,000` is one number (1000), not 1 and 000; ungrounded when absent from the sources."""
    assert ungrounded_numbers("Bring 1,000 cups.", ["500 cups"]) == ("1,000",)


def test_digits_joined_to_letters_or_hyphens_count():
    """Covers: AC-1 (right/boundary). `5gal` is 5 and `1-gallon` is 1 (but 1 is ignored); `9-gallon` is 9."""
    for answer, digit in (("Use the 5gal one.", "5"), ("A 9-gallon tub", "9")):
        result = ungrounded_numbers(answer, [""])
        assert len(result) == 1 and result[0].startswith(digit)
        assert ungrounded_numbers(answer, [f"{digit} gal"]) == ()
    assert ungrounded_numbers("A 1-gallon tub", [""]) == ()


def test_trailing_period_is_not_a_decimal_part():
    """Covers: AC-1 (boundary). `3.` at the end of a sentence (not at a line start) is the number 3."""
    assert ungrounded_numbers("You need 3.", [""]) == ("3",)
    assert ungrounded_numbers("You need 3.", ["3 cups"]) == ()


# ---- what is ignored in the answer -------------------------------------------

@pytest.mark.parametrize("answer", ["Make 1 batch.", "1 cup", "Use 1.0 gallon.", "Use 1.00 gallon.", "01 cup"])
def test_value_one_is_ignored(answer):
    """Covers: AC-1 (right/boundary), EC-1. The value 1 is never ungrounded (also written 1.0)."""
    assert ungrounded_numbers(answer, [""]) == ()


@pytest.mark.parametrize(
    "answer",
    ["1. Pour it.", " 2) Stir.", "- 3. Mix.", "* 4) Mix.", "10. Serve.", "   -   12) Serve."],
)
def test_list_markers_at_line_start_are_ignored(answer):
    """Covers: AC-1 (right), EC-1, EC-4. A list marker (optional spaces/bullet, digits, then . or )) at the start of a line is ignored."""
    assert ungrounded_numbers(answer, [""]) == ()


def test_list_marker_on_a_later_line():
    """Covers: AC-1 (right), EC-4. The marker rule applies at the start of every line, not only the first."""
    assert ungrounded_numbers("Steps:\n3. Pour\n4) Stir", [""]) == ()


def test_list_marker_does_not_hide_numbers_after_it():
    """Covers: AC-1 (boundary), EC-4. Only the marker is ignored; a number later in the same line still counts."""
    assert ungrounded_numbers("1. Use 4 cups.", [""]) == ("4",)


def test_marker_text_not_at_line_start_counts():
    """Covers: AC-1 (wrong), EC-4. `Step 2. Stir` is not a marker (it is not at the start of the line)."""
    assert ungrounded_numbers("Step 2. Stir", [""]) == ("2",)


def test_bullet_then_marker_ignored():
    """Covers: AC-1 (right), EC-4. `  - 3) Pour` is a list marker and gives no number."""
    assert ungrounded_numbers("  - 3) Pour", [""]) == ()


def test_digits_without_marker_punctuation_count():
    """Covers: AC-1 (wrong), EC-4 (boundary). Digits at a line start with no `.` or `)` after them are a number."""
    assert ungrounded_numbers("3 cups", [""]) == ("3",)


@pytest.mark.parametrize(
    "answer",
    ["See data/supplies/coffee2.md.", "See data/2024/menu.md.", "Per `recipes/v7.md`.", "(source: data/a9.md)"],
)
def test_digits_inside_a_cited_md_path_are_ignored(answer):
    """Covers: AC-1 (right), EC-1. Digits inside a cited .md path are not numbers."""
    assert ungrounded_numbers(answer, [""]) == ()


def test_number_next_to_a_citation_still_counts():
    """Covers: AC-1 (boundary). Ignoring a citation does not hide a number elsewhere in the same answer."""
    assert ungrounded_numbers("Use 3 cups (see data/supplies/coffee.md).", [""]) == ("3",)


# ---- grounding against the sources -------------------------------------------

@pytest.mark.parametrize(
    "answer, sources",
    [
        ("Use 7.0 oz", ["7 oz"]),
        ("Use 17.50 oz", ["17.5 oz"]),
        ("Use Twelve trays", ["12 trays"]),
        ("Use 12 trays", ["twelve trays"]),
        ("Use two cups", ["2 cups"]),
        ("Use 2 cups", ["Two cups"]),
        ("Use 35 oz", ["35.0 oz"]),
        ("Use 1000 cups", ["1,000 cups"]),
    ],
)
def test_values_compare_as_numbers(answer, sources):
    """Covers: AC-1 (right), EC-2. Grounding compares values: 7.0 = 7, 17.50 = 17.5, Twelve = 12, two = 2, 1,000 = 1000."""
    assert ungrounded_numbers(answer, sources) == ()


def test_different_values_do_not_match():
    """Covers: AC-1 (wrong), EC-2. 17.5 is not 17, and 12 is not 120."""
    assert ungrounded_numbers("Use 17.5 oz", ["17 oz"]) == ("17.5",)
    assert ungrounded_numbers("Use 12 oz", ["120 oz"]) == ("12",)


def test_any_source_can_ground_a_number():
    """Covers: AC-1 (right). A number found in any one of several sources is grounded."""
    assert ungrounded_numbers("Use 4 cups and 9 trays", ["no digits", "4 cups", "9 trays"]) == ()


def test_each_number_needs_its_own_source():
    """Covers: AC-1 (wrong). With 4 grounded and 9 not, only 9 is returned."""
    assert ungrounded_numbers("Use 4 cups and 9 trays", ["4 cups"]) == ("9",)


def test_nothing_is_ignored_in_sources():
    """Covers: AC-1 (boundary), EC-4. In the sources list markers and paths count: `2.` and `coffee2.md` ground a 2."""
    assert ungrounded_numbers("Use 2 cups", ["1. Pour\n2. Stir"]) == ()
    assert ungrounded_numbers("Use 2 cups", ["data/supplies/coffee2.md"]) == ()


def test_number_word_in_sources_grounds_digits():
    """Covers: AC-1 (right), EC-2. A source written `twelve` grounds `12` in the answer."""
    assert ungrounded_numbers("Make 12 gallons", ["Make twelve gallons"]) == ()


# ---- EC-3: order and duplicates ----------------------------------------------

def test_duplicates_removed_and_order_kept():
    """Covers: AC-1 (right), EC-3. `3 cups, then 4 cups, then 3 cups` gives ("3", "4")."""
    assert ungrounded_numbers("3 cups, then 4 cups, then 3 cups", [""]) == ("3", "4")


def test_order_is_first_appearance_not_value():
    """Covers: AC-1 (boundary), EC-3. Results follow the order of first appearance, not sorted."""
    assert ungrounded_numbers("Use 9, then 3, then 6", [""]) == ("9", "3", "6")


# ---- EC-5: empty and odd input ------------------------------------------------

def test_no_numbers_gives_empty():
    """Covers: AC-1 (right), EC-5. An answer with no numbers gives ()."""
    assert ungrounded_numbers("Bring the lemons.", ["5 cups"]) == ()


def test_empty_answer_gives_empty():
    """Covers: AC-1 (boundary), EC-5. An empty answer gives ()."""
    assert ungrounded_numbers("", ["5 cups"]) == ()


def test_empty_sources_list_leaves_numbers_ungrounded():
    """Covers: AC-1 (boundary), EC-5. An empty sources list grounds nothing."""
    assert ungrounded_numbers("Use 5 cups", []) == ("5",)
    assert ungrounded_numbers("No digits", []) == ()


def test_none_answer_gives_empty_and_does_not_raise():
    """Covers: AC-1 (wrong), EC-5. A None answer gives ()."""
    assert ungrounded_numbers(None, ["5 cups"]) == ()  # type: ignore[arg-type]


def test_none_inside_sources_does_not_raise():
    """Covers: AC-1 (wrong), EC-5. A None entry among the sources never raises; real entries still ground."""
    assert ungrounded_numbers("Use 5 cups", [None, "5 cups"]) == ()  # type: ignore[list-item]
    assert ungrounded_numbers("Use 5 cups", [None]) == ("5",)  # type: ignore[list-item]


def test_whitespace_only_answer():
    """Covers: AC-1 (boundary), EC-5. A whitespace-only answer gives ()."""
    assert ungrounded_numbers("  \n\t ", [""]) == ()


# ---- NFR-5: deterministic, pure ----------------------------------------------

def test_same_input_same_output():
    """Covers: NFR-5 (right). Repeated calls give identical results and do not change the sources."""
    sources = ["Decaf: 9 gal."]
    first = ungrounded_numbers("Use 3 cups and 9 gal and 4 trays", sources)
    second = ungrounded_numbers("Use 3 cups and 9 gal and 4 trays", sources)
    assert first == second == ("3", "4")
    assert sources == ["Decaf: 9 gal."]


def test_accepts_tuples_as_sources():
    """Covers: AC-1 (right). `sources` may be any Sequence, such as a tuple."""
    assert ungrounded_numbers("Use 4 cups", ("4 cups",)) == ()


def test_prints_nothing(capsys):
    """Covers: AC-1 (right). The function prints nothing."""
    ungrounded_numbers("Use 3 cups", [""])
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""

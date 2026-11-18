"""Spec 017 AC-2: `unknown_sources` (section 4.2, EC-7 to EC-10, NFR-5). Unit; pure; no model, no files."""

from __future__ import annotations

import pytest

from blc.judge import unknown_sources

COFFEE = ["data/supplies/coffee.md"]


# ---- EC-7: every row of the section 4.2 table --------------------------------

@pytest.mark.parametrize(
    "answer, allowed, expected",
    [
        ("(source: data/supplies/coffee.md)", COFFEE, ()),
        ("See `coffee.md`.", COFFEE, ()),
        ("See data/supplies/syrups.md and data/supplies/coffee.md.", COFFEE, ("data/supplies/syrups.md",)),
        ("Per lemonade.md", [], ("lemonade.md",)),
        ("No citation here.", [], ()),
    ],
)
def test_section_4_2_table(answer, allowed, expected):
    """Covers: AC-2 (right/wrong), EC-7. Each row of the section 4.2 table gives its listed result."""
    assert unknown_sources(answer, allowed) == expected


def test_returns_a_tuple():
    """Covers: AC-2 (right). The result is a tuple, also when empty."""
    assert isinstance(unknown_sources("See a.md", []), tuple)
    assert isinstance(unknown_sources("Nothing", []), tuple)


# ---- matching at a "/" boundary ----------------------------------------------

LEMONADE = ["data/recipes/lemonade.md"]


@pytest.mark.parametrize("cited", ["lemonade.md", "recipes/lemonade.md", "data/recipes/lemonade.md"])
def test_suffix_at_slash_boundary_is_allowed(cited):
    """Covers: AC-2 (right), EC-7. `lemonade.md` and `recipes/lemonade.md` both match data/recipes/lemonade.md."""
    assert unknown_sources(f"See {cited}.", LEMONADE) == ()


def test_partial_file_name_is_not_allowed():
    """Covers: AC-2 (wrong/boundary), EC-7. `ade.md` does not match data/recipes/lemonade.md (not at a / boundary)."""
    assert unknown_sources("See ade.md.", LEMONADE) == ("ade.md",)


def test_cited_longer_than_allowed_matches_when_allowed_is_the_suffix():
    """Covers: AC-2 (right), EC-7. One ends with the other in either direction: cited data/recipes/lemonade.md vs allowed lemonade.md."""
    assert unknown_sources("See data/recipes/lemonade.md.", ["lemonade.md"]) == ()


def test_longer_prefix_without_slash_boundary_is_unknown():
    """Covers: AC-2 (wrong/boundary), EC-7. `xlemonade.md` is not `lemonade.md` (no / boundary)."""
    assert unknown_sources("See xlemonade.md.", ["lemonade.md"]) == ("xlemonade.md",)


def test_different_directory_same_name_other_prefix_is_unknown():
    """Covers: AC-2 (wrong), EC-7. `other/syrups.md` does not match `data/supplies/syrups.md` (neither ends with the other)."""
    assert unknown_sources("See other/syrups.md.", ["data/supplies/syrups.md"]) == ("other/syrups.md",)


def test_any_allowed_entry_can_match():
    """Covers: AC-2 (right). A citation matching any one of several allowed entries is allowed."""
    allowed = ["data/supplies/syrups.md", "data/supplies/coffee.md", "data/recipes/lemonade.md"]
    assert unknown_sources("See coffee.md and lemonade.md and syrups.md.", allowed) == ()


# ---- what a citation is --------------------------------------------------------

@pytest.mark.parametrize(
    "answer",
    [
        "See data/x.md.",
        "See data/x.md,",
        "(data/x.md)",
        "[data/x.md]",
        "`data/x.md`",
        '"data/x.md".',
        "'data/x.md'",
        "**data/x.md**",
        "(source: data/x.md);",
    ],
)
def test_wrapped_and_punctuated_citations_give_the_bare_path(answer):
    """Covers: AC-2 (right), EC-9. Brackets, parentheses, backticks, quotes and trailing punctuation are removed."""
    assert unknown_sources(answer, []) == ("data/x.md",)


def test_underscores_hyphens_digits_in_names():
    """Covers: AC-2 (right/boundary), EC-9. Letters, digits, _, - and . are part of a citation."""
    assert unknown_sources("See data/hot_water-2.v1.md now", []) == ("data/hot_water-2.v1.md",)


def test_md_ending_found_in_any_case():
    """Covers: AC-2 (right), EC-8. The .md ending is found in any case (`.MD`) and the citation is returned as written."""
    assert unknown_sources("See coffee.MD", []) == ("coffee.MD",)
    assert unknown_sources("See notes.Md", []) == ("notes.Md",)


def test_text_not_ending_in_md_is_not_a_citation():
    """Covers: AC-2 (wrong), EC-7. Words that merely contain `md` or end in something else are not citations."""
    assert unknown_sources("See coffee.mdx and readmd and file.markdown and a.mp3", []) == ()


def test_bare_md_word_without_name_is_not_flagged_as_a_known_file():
    """Covers: AC-2 (boundary). The word `markdown` and plain prose give no citations."""
    assert unknown_sources("It is written in markdown.", []) == ()


# ---- EC-8: case-sensitive paths ------------------------------------------------

def test_paths_compare_case_sensitively():
    """Covers: AC-2 (wrong), EC-8. DATA/SUPPLIES/COFFEE.MD does not match data/supplies/coffee.md and is returned as written."""
    assert unknown_sources("See DATA/SUPPLIES/COFFEE.MD", COFFEE) == ("DATA/SUPPLIES/COFFEE.MD",)


def test_file_name_case_differs_is_unknown():
    """Covers: AC-2 (wrong), EC-8. `Coffee.md` is not `coffee.md`."""
    assert unknown_sources("See Coffee.md", COFFEE) == ("Coffee.md",)


# ---- EC-9: duplicates and order ------------------------------------------------

def test_duplicates_removed_and_order_kept():
    """Covers: AC-2 (right), EC-9. `a.md, b.md, a.md` with no allowed files gives ("a.md", "b.md")."""
    assert unknown_sources("a.md, b.md, a.md", []) == ("a.md", "b.md")


def test_order_is_first_appearance():
    """Covers: AC-2 (boundary), EC-9. The order is the order of first appearance, not alphabetical."""
    assert unknown_sources("See z.md then a.md then m.md", []) == ("z.md", "a.md", "m.md")


def test_allowed_citations_are_dropped_among_unknown_ones():
    """Covers: AC-2 (right), EC-9. Only the unknown citations are returned, in order, without duplicates."""
    assert unknown_sources("x.md, coffee.md, y.md, x.md", COFFEE) == ("x.md", "y.md")


# ---- EC-10: odd input ----------------------------------------------------------

def test_none_answer_gives_empty():
    """Covers: AC-2 (wrong), EC-10. A None answer gives () and does not raise."""
    assert unknown_sources(None, COFFEE) == ()  # type: ignore[arg-type]


def test_empty_answer_gives_empty():
    """Covers: AC-2 (boundary), EC-10. An empty answer gives ()."""
    assert unknown_sources("", COFFEE) == ()


def test_empty_allowed_makes_every_citation_unknown():
    """Covers: AC-2 (boundary), EC-7. With allowed == [] (a TOOL-only answer) any citation is unknown."""
    assert unknown_sources("(data/supplies/coffee.md)", []) == ("data/supplies/coffee.md",)


def test_none_inside_allowed_does_not_raise():
    """Covers: AC-2 (wrong), EC-10. A None entry in allowed never raises; real entries still match."""
    assert unknown_sources("See coffee.md", [None, "data/supplies/coffee.md"]) == ()  # type: ignore[list-item]


def test_whitespace_and_symbols_only():
    """Covers: AC-2 (boundary), EC-10. Whitespace or symbols alone never raise and give ()."""
    assert unknown_sources("  \n\t", []) == ()
    assert unknown_sources("!!! ... ???", []) == ()


# ---- NFR-5 ---------------------------------------------------------------------

def test_same_input_same_output():
    """Covers: NFR-5 (right). Repeated calls give identical results and leave `allowed` unchanged."""
    allowed = list(COFFEE)
    first = unknown_sources("See a.md and coffee.md and b.md", allowed)
    assert first == unknown_sources("See a.md and coffee.md and b.md", allowed) == ("a.md", "b.md")
    assert allowed == COFFEE


def test_prints_nothing(capsys):
    """Covers: AC-2 (right). The function prints nothing."""
    unknown_sources("See a.md", [])
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""

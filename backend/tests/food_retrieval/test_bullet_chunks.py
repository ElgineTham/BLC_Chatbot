"""CHUNK: per-bullet chunking by chunk_markdown (spec 026 section 6.1)."""

from __future__ import annotations

import pytest

from food_helpers import SECTION_HEADINGS, bold_items, h2_headings_in, has_heading, section_text
from ingest import PER_BULLET_SOURCES, chunk_markdown

DOC = """# Menu

Intro line.

## Bakery
- **Bagels**: on the rack.
  Served with cream cheese.
- **Cream cheese**: in the cooler.

## Notes
Plain paragraph.
"""

BAGELS = "- **Bagels**: on the rack."
CONT = "Served with cream cheese."
CREAM = "- **Cream cheese**: in the cooler."


def lines_of(chunk: str) -> list[str]:
    return [ln.strip() for ln in chunk.splitlines()]


def chunks_with_line(chunks: list[str], line: str) -> list[str]:
    return [c for c in chunks if line.strip() in lines_of(c)]


def chunk_containing(chunks: list[str], needle: str) -> str:
    found = [c for c in chunks if needle in c]
    assert found, f"no chunk contains {needle!r}"
    return found[0]


@pytest.fixture(scope="module")
def doc_chunks():
    return chunk_markdown(DOC, per_bullet=True)


@pytest.fixture(scope="module")
def food_bullet_chunks(food_text):
    return chunk_markdown(food_text, per_bullet=True)


# ---- DOC, unit ----

def test_each_bullet_in_exactly_one_separate_chunk(doc_chunks):
    """Covers: AC-1 (right), CHUNK-1. Bagels and Cream cheese bullets are in different chunks, each line in exactly one."""
    assert len(chunks_with_line(doc_chunks, BAGELS)) == 1
    assert len(chunks_with_line(doc_chunks, CREAM)) == 1
    assert chunks_with_line(doc_chunks, BAGELS)[0] is not chunks_with_line(doc_chunks, CREAM)[0]


def test_bullet_chunk_holds_no_other_bullet(doc_chunks):
    """Covers: AC-1 (wrong), CHUNK-1. A bullet's chunk must not contain the sibling bullet."""
    assert "Cream cheese**" not in chunk_containing(doc_chunks, BAGELS).replace(CONT, "")
    assert "Bagels" not in chunk_containing(doc_chunks, CREAM)


def test_bullet_chunk_has_title_then_heading_then_bullet(doc_chunks):
    """Covers: AC-2 (right), CHUNK-2. Bagels chunk has '# Menu', then '## Bakery', then the bullet, in order."""
    c = chunk_containing(doc_chunks, BAGELS)
    ls = lines_of(c)
    assert ls.index("# Menu") < ls.index("## Bakery") < ls.index(BAGELS)


def test_second_bullet_chunk_also_has_context(doc_chunks):
    """Covers: AC-2 (right), CHUNK-2. Every bullet chunk carries the context, not only the first."""
    ls = lines_of(chunk_containing(doc_chunks, CREAM))
    assert ls.index("# Menu") < ls.index("## Bakery") < ls.index(CREAM)


def test_non_bullet_section_chunk_has_context(doc_chunks):
    """Covers: AC-2 (right), AC-4 (right), CHUNK-3. Notes chunk has title, heading and paragraph in order."""
    ls = lines_of(chunk_containing(doc_chunks, "Plain paragraph."))
    assert ls.index("# Menu") < ls.index("## Notes") < ls.index("Plain paragraph.")


def test_continuation_stays_with_its_bullet(doc_chunks):
    """Covers: AC-3 (right), CHUNK-4. Continuation line is with Bagels and not in the Cream cheese chunk."""
    bagels = chunk_containing(doc_chunks, BAGELS)
    cream = chunk_containing(doc_chunks, CREAM)
    assert CONT in lines_of(bagels)
    assert CONT not in lines_of(cream)
    assert len(chunks_with_line(doc_chunks, CONT)) == 1


def test_no_non_blank_line_lost(doc_chunks):
    """Covers: AC-4 (right), CHUNK-5. Every non-blank line, including 'Intro line.', is in some chunk."""
    all_lines = {ln for c in doc_chunks for ln in lines_of(c)}
    for line in DOC.splitlines():
        if line.strip():
            assert line.strip() in all_lines, f"lost line: {line!r}"
    assert "Intro line." in all_lines


def test_short_doc_still_split(doc_chunks):
    """Covers: AC-5 (right), CHUNK-6. A tiny document is still split into more than one chunk."""
    assert len(doc_chunks) > 1


def test_default_equals_per_bullet_false():
    """Covers: AC-6 (right), CHUNK-7. The default call equals per_bullet=False."""
    assert chunk_markdown(DOC) == chunk_markdown(DOC, per_bullet=False)


def test_per_bullet_false_differs_from_true_on_short_doc(doc_chunks):
    """Covers: AC-6 (wrong), AC-5. The flag matters: per_bullet=False does not split bullets of a short doc apart."""
    plain = chunk_markdown(DOC, per_bullet=False)
    assert len(plain) < len(doc_chunks)
    assert not any(c for c in plain if BAGELS in c and CREAM not in c)


def test_per_bullet_false_does_not_gain_context_copies():
    """Covers: AC-6 (boundary). per_bullet=False never repeats the title line in more than one chunk of a short doc."""
    plain = chunk_markdown(DOC, per_bullet=False)
    assert sum(c.count("# Menu") for c in plain) == 1


# ---- extra boundaries ----

@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_blank_input_per_bullet_gives_no_blank_chunks(text):
    """Covers: AC-4 (boundary), extra. Empty or whitespace-only input yields no blank chunk with per_bullet=True."""
    assert all(c.strip() for c in chunk_markdown(text, per_bullet=True))


def test_single_bullet_section():
    """Covers: AC-1/AC-2 (boundary), extra. A section with one bullet gives a chunk with context and that bullet."""
    text = "# T\n\n## S\n- **Only**: here.\n"
    chunks = chunk_markdown(text, per_bullet=True)
    ls = lines_of(chunk_containing(chunks, "- **Only**: here."))
    assert ls.index("# T") < ls.index("## S") < ls.index("- **Only**: here.")
    assert len(chunks_with_line(chunks, "- **Only**: here.")) == 1


def test_context_uses_own_section_heading():
    """Covers: AC-2 (wrong), extra. A bullet chunk carries only its own section heading, not another section's."""
    text = "# T\n\n## A\n- **One**: a.\n\n## B\n- **Two**: b.\n"
    chunks = chunk_markdown(text, per_bullet=True)
    one = lines_of(chunk_containing(chunks, "**One**"))
    two = lines_of(chunk_containing(chunks, "**Two**"))
    assert "## A" in one and "## B" not in one
    assert "## B" in two and "## A" not in two


def test_multiple_continuation_lines_kept():
    """Covers: AC-3 (boundary), extra. Several continuation lines all stay with their bullet."""
    text = "# T\n\n## S\n- **X**: x.\n  line two.\n  line three.\n- **Y**: y.\n"
    chunks = chunk_markdown(text, per_bullet=True)
    x = lines_of(chunk_containing(chunks, "- **X**: x."))
    assert "line two." in x and "line three." in x
    assert "line two." not in lines_of(chunk_containing(chunks, "- **Y**: y."))


def test_section_without_bullets_kept_among_bulleted_sections():
    """Covers: AC-4 (right), extra. Plain text under a bullet-less section is kept when other sections have bullets."""
    text = "# T\n\n## A\n- **One**: a.\n\n## B\nJust prose here.\n"
    chunks = chunk_markdown(text, per_bullet=True)
    assert "Just prose here." in lines_of(chunk_containing(chunks, "Just prose here."))
    assert "## B" in lines_of(chunk_containing(chunks, "Just prose here."))


# ---- food.md, unit ----

def test_food_per_bullet_false_sections_each_head_one_chunk(food_text):
    """Covers: AC-6 (right), CHUNK-8. With per_bullet=False each of the nine headings heads exactly one chunk."""
    chunks = chunk_markdown(food_text, per_bullet=False)
    for heading in SECTION_HEADINGS:
        n = sum(1 for c in chunks if has_heading(c, heading))
        assert n == 1, f"'## {heading}' heads {n} chunks"


def test_food_per_bullet_false_no_chunk_with_two_h2(food_text):
    """Covers: AC-6 (wrong), CHUNK-8. No chunk has two ## headings with per_bullet=False."""
    chunks = chunk_markdown(food_text, per_bullet=False)
    assert not [c for c in chunks if len(h2_headings_in(c)) > 1]


def test_food_each_bullet_line_in_exactly_one_chunk(food_text, food_bullet_chunks):
    """Covers: AC-1 (right), CHUNK-9. Each '- ' line of food.md is in exactly one chunk (per occurrence in the file)."""
    bullets = [ln.strip() for ln in food_text.splitlines() if ln.startswith("- ")]
    assert bullets
    for b in set(bullets):
        expected = bullets.count(b)
        got = sum(lines_of(c).count(b) for c in food_bullet_chunks)
        assert got == expected, f"bullet {b[:50]!r}: in {got} chunk lines, file has {expected}"
        assert all(lines_of(c).count(b) <= 1 for c in food_bullet_chunks)


def test_food_no_chunk_has_two_bullets_of_one_section(food_text, food_bullet_chunks):
    """Covers: AC-1 (wrong), CHUNK-9. No chunk holds two top-level bullets."""
    bad = [i for i, c in enumerate(food_bullet_chunks)
           if sum(1 for ln in c.splitlines() if ln.startswith("- ")) > 1]
    assert not bad, f"chunks with more than one bullet: {bad}"


def test_food_more_chunks_than_sections(food_bullet_chunks):
    """Covers: AC-1 (boundary), extra. Per-bullet chunking produces many more chunks than sections."""
    assert len(food_bullet_chunks) > len(SECTION_HEADINGS)


def test_food_dijon_chunk_is_isolated_with_context(food_bullet_chunks):
    """Covers: AC-1 (right), AC-2 (right), CHUNK-10. Dijon mustard chunk has title, '## Lunch', and no Mayonnaise."""
    dijon = [c for c in food_bullet_chunks if "**Dijon mustard**" in c]
    assert dijon, "no chunk contains **Dijon mustard**"
    for c in dijon:
        ls = [ln for ln in c.splitlines()]
        title_idx = next((i for i, ln in enumerate(ls) if ln.startswith("# ")), None)
        assert title_idx is not None, "chunk lacks the # title line"
        assert has_heading(c, "Lunch")
        assert title_idx < ls.index("## Lunch")
        assert "Mayonnaise" not in c


def test_food_every_bullet_chunk_has_title_and_own_section(food_text, food_bullet_chunks):
    """Covers: AC-2 (right), CHUNK-10. Each chunk with a bullet starts context with '# ' title and its own section heading."""
    for c in food_bullet_chunks:
        bullet_lines = [ln for ln in c.splitlines() if ln.startswith("- ")]
        if not bullet_lines:
            continue
        ls = c.splitlines()
        heads = [i for i, ln in enumerate(ls) if ln.startswith("## ")]
        titles = [i for i, ln in enumerate(ls) if ln.startswith("# ")]
        assert len(heads) == 1 and titles, f"missing context in chunk: {c[:80]!r}"
        heading = ls[heads[0]][3:].strip()
        assert titles[0] < heads[0] < ls.index(bullet_lines[0])
        assert bullet_lines[0].strip() in section_text(food_text, heading)


def test_food_no_non_blank_line_lost(food_text, food_bullet_chunks):
    """Covers: AC-4 (right), CHUNK-11. Every non-blank line of food.md appears (stripped) in some chunk."""
    all_lines = {ln for c in food_bullet_chunks for ln in lines_of(c)}
    lost = [ln for ln in food_text.splitlines() if ln.strip() and ln.strip() not in all_lines]
    assert not lost, f"lost lines: {lost[:5]}"


def test_food_every_item_name_in_some_chunk(food_text, food_bullet_chunks):
    """Covers: AC-4 (right), CHUNK-11. Every **item** name is in some chunk."""
    items = bold_items(food_text)
    assert items
    missing = [i for i in items if not any(i in c for c in food_bullet_chunks)]
    assert not missing, f"item names lost: {missing}"


def test_per_bullet_sources_constant():
    """Covers: AC-7 (right), CHUNK-12. PER_BULLET_SOURCES is exactly the food.md source."""
    assert tuple(PER_BULLET_SOURCES) == ("data/pull_sheet/menu/food.md",)

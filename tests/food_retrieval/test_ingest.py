"""ING: chunking and ingest of data/pull_sheet/menu/food.md (spec 025 section 6.1)."""

from __future__ import annotations

import pytest

from food_helpers import (
    SECTION_HEADINGS,
    bold_items,
    h2_headings_in,
    has_heading,
)
from ingest import chunk_markdown


@pytest.fixture(scope="module")
def chunks(food_text):
    # Spec 026 AC-6: ING-3/ING-4 now apply to the per_bullet=False call.
    return chunk_markdown(food_text, per_bullet=False)


def test_food_file_has_the_nine_sections(food_text):
    """Covers: AC-3 (right, precondition). food.md has exactly the nine named ## sections."""
    assert h2_headings_in(food_text) == SECTION_HEADINGS


def test_chunks_non_empty_and_non_blank(chunks):
    """Covers: AC-2 (right), ING-1. At least one chunk and every chunk is non-blank."""
    assert chunks
    assert all(isinstance(c, str) and c.strip() for c in chunks)


@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_blank_input_gives_no_blank_chunks(text):
    """Covers: AC-2 (boundary). Empty or whitespace-only text never yields a blank chunk."""
    assert all(c.strip() for c in chunk_markdown(text))


def test_every_bold_item_is_in_some_chunk(food_text, chunks):
    """Covers: AC-2 (right), ING-2. Each **item** name appears in at least one chunk."""
    items = bold_items(food_text)
    assert items, "food.md should contain bolded item names"
    missing = [i for i in items if not any(i in c for c in chunks)]
    assert not missing, f"item names lost by chunking: {missing}"


@pytest.mark.parametrize("heading", SECTION_HEADINGS)
def test_each_section_heads_exactly_one_chunk(chunks, heading):
    """Covers: AC-3 (right), ING-3. Each ## section is the heading of exactly one chunk."""
    count = sum(1 for c in chunks if has_heading(c, heading))
    assert count == 1, f"'## {heading}' heads {count} chunks, expected 1"


def test_no_chunk_has_two_h2_headings(chunks):
    """Covers: AC-3 (wrong), ING-4. No chunk contains two ## headings."""
    bad = [i for i, c in enumerate(chunks) if len(h2_headings_in(c)) > 1]
    assert not bad, f"chunks with two ## headings: {bad}"

# Integration tests that used ingest_file moved to test_bullet_store.py (spec 026 AC-7):
# food.md is now stored with per_bullet=True chunking.

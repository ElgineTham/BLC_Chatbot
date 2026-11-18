"""Spec 036 section 6.1: content_hash and plan_changes (pure functions)."""

from __future__ import annotations

import hashlib

from ingest import HASH_KEY, IngestPlan, content_hash, plan_changes


def _all(plan):
    return plan.new + plan.updated + plan.unchanged + plan.deleted


def test_hash_key_value():
    """Covers: AC-9 (right). HASH_KEY is 'content_hash'."""
    assert HASH_KEY == "content_hash"


def test_content_hash_known_vector():
    """Covers: AC-1 (right), PLAN-1. SHA-256 of b'abc'."""
    assert content_hash(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_content_hash_empty_bytes_boundary():
    """Covers: AC-1 (boundary). Empty input hashes to the SHA-256 of nothing."""
    assert content_hash(b"") == hashlib.sha256(b"").hexdigest()


def test_content_hash_format_lowercase_hex_64():
    """Covers: AC-1 (right). 64 lowercase hex chars."""
    h = content_hash("Ünïcode".encode("utf-8"))
    assert len(h) == 64
    assert h == h.lower()
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_equal_bytes_equal_hash():
    """Covers: AC-1 (right). Same bytes give the same hash."""
    assert content_hash(b"same") == content_hash(bytes(bytearray(b"same")))


def test_content_hash_line_endings_differ():
    """Covers: AC-1 (wrong), PLAN-2. LF and CRLF give different hashes."""
    assert content_hash(b"a\n") != content_hash(b"a\r\n")


def test_content_hash_single_byte_difference():
    """Covers: AC-1 (wrong). One differing byte changes the hash."""
    assert content_hash(b"abc") != content_hash(b"abd")


def test_plan_new():
    """Covers: AC-2 (right), PLAN-3. Only in current -> new."""
    p = plan_changes({"a": "h1"}, {})
    assert p.new == ("a",)
    assert p.updated == () and p.unchanged == () and p.deleted == ()


def test_plan_unchanged():
    """Covers: AC-2 (right), PLAN-4. Equal hashes -> unchanged."""
    p = plan_changes({"a": "h1"}, {"a": "h1"})
    assert p.unchanged == ("a",)
    assert p.new == () and p.updated == () and p.deleted == ()


def test_plan_updated_on_different_hash():
    """Covers: AC-2 (right), PLAN-5. Differing hashes -> updated."""
    p = plan_changes({"a": "h2"}, {"a": "h1"})
    assert p.updated == ("a",)
    assert p.new == () and p.unchanged == () and p.deleted == ()


def test_plan_updated_when_stored_hash_none():
    """Covers: AC-2 (boundary), AC-8 (right), PLAN-6. Stored None -> updated, not new/unchanged."""
    p = plan_changes({"a": "h1"}, {"a": None})
    assert p.updated == ("a",)
    assert p.new == () and p.unchanged == () and p.deleted == ()


def test_plan_deleted():
    """Covers: AC-2 (right), PLAN-7. Only in stored -> deleted."""
    p = plan_changes({}, {"a": "h1"})
    assert p.deleted == ("a",)
    assert p.new == () and p.updated == () and p.unchanged == ()


def test_plan_deleted_with_none_hash():
    """Covers: AC-2 (boundary). A stored-only source with hash None is still deleted."""
    p = plan_changes({}, {"a": None})
    assert p.deleted == ("a",)


def test_plan_empty_inputs():
    """Covers: AC-2 (boundary). Both empty -> all-empty plan."""
    p = plan_changes({}, {})
    assert p == IngestPlan(new=(), updated=(), unchanged=(), deleted=())


def test_plan_mixed_sorted_and_exclusive():
    """Covers: AC-2 (right), PLAN-8. c,a new; b unchanged; d deleted; sorted; each source once."""
    p = plan_changes({"c": "h", "a": "h", "b": "h"}, {"b": "h", "d": "h"})
    assert p.new == ("a", "c")
    assert p.unchanged == ("b",)
    assert p.deleted == ("d",)
    assert p.updated == ()
    allsrc = _all(p)
    assert sorted(allsrc) == ["a", "b", "c", "d"]
    assert len(allsrc) == len(set(allsrc))


def test_plan_every_tuple_sorted_all_kinds():
    """Covers: AC-2 (boundary). Each of the four tuples is sorted ascending, regardless of input order."""
    current = {"u3": "n", "u1": "n", "k2": "s", "k1": "s", "n2": "s", "n1": "s"}
    stored = {"u3": "o", "u1": "o", "k2": "s", "k1": "s", "d2": "s", "d1": None}
    p = plan_changes(current, stored)
    assert p.new == ("n1", "n2")
    assert p.updated == ("u1", "u3")
    assert p.unchanged == ("k1", "k2")
    assert p.deleted == ("d1", "d2")
    for t in (p.new, p.updated, p.unchanged, p.deleted):
        assert isinstance(t, tuple)


def test_plan_is_frozen():
    """Covers: AC-2 (wrong). IngestPlan is a frozen dataclass; assignment is rejected."""
    import dataclasses

    import pytest

    p = plan_changes({"a": "h"}, {})
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.new = ("z",)  # type: ignore[misc]

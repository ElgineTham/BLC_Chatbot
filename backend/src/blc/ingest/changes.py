"""Content-hash change detection for ingest (spec 036). Pure: no I/O."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

HASH_KEY = "content_hash"


@dataclass(frozen=True)
class IngestPlan:
    new: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    deleted: tuple[str, ...]


def content_hash(data: bytes) -> str:
    """Lowercase hex SHA-256 of the raw bytes (64 chars)."""
    return hashlib.sha256(data).hexdigest()


def plan_changes(
    current: Mapping[str, str], stored: Mapping[str, str | None]
) -> IngestPlan:
    """Classify each source as new, updated, unchanged or deleted."""
    new: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    for source, digest in current.items():
        if source not in stored:
            new.append(source)
        elif stored[source] == digest:
            unchanged.append(source)
        else:
            updated.append(source)
    deleted = [source for source in stored if source not in current]
    return IngestPlan(
        new=tuple(sorted(new)),
        updated=tuple(sorted(updated)),
        unchanged=tuple(sorted(unchanged)),
        deleted=tuple(sorted(deleted)),
    )

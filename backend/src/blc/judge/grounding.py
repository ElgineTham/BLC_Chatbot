"""Code checks that an answer adds no numbers or sources it was not given (spec 017)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

NUMBER_WORDS: dict[str, int] = {
    word: value
    for value, word in enumerate(
        (
            "two three four five six seven eight nine ten eleven twelve thirteen "
            "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
        ).split(),
        start=2,
    )
}
IGNORED_VALUE = Decimal(1)

_NUMBER_RE = re.compile(
    r"(?P<digits>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"|\b(?P<word>" + "|".join(NUMBER_WORDS) + r")\b",
    re.IGNORECASE,
)
_LIST_MARKER_RE = re.compile(r"^[ \t]*[-*]?[ \t]*\d+[.)](?!\d)", re.MULTILINE)
_CITATION_RE = re.compile(r"[A-Za-z0-9_\-./]+\.md(?![A-Za-z0-9_/\-])", re.IGNORECASE)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _numbers(text: str) -> list[tuple[str, Decimal]]:
    found: list[tuple[str, Decimal]] = []
    for match in _NUMBER_RE.finditer(text):
        if match.group("digits") is not None:
            written = match.group("digits")
            value = Decimal(written.replace(",", ""))
        else:
            written = match.group("word")
            value = Decimal(NUMBER_WORDS[written.lower()])
        found.append((written, value))
    return found


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def ungrounded_numbers(answer: str, sources: Sequence[str]) -> tuple[str, ...]:
    """The numbers in answer whose value appears in none of sources."""
    try:
        text = _CITATION_RE.sub(_blank, _text(answer))
        text = _LIST_MARKER_RE.sub(_blank, text)
        known = {value for source in (sources or ()) for _, value in _numbers(_text(source))}
        missing: list[str] = []
        for written, value in _numbers(text):
            if value == IGNORED_VALUE or value in known or written in missing:
                continue
            missing.append(written)
        return tuple(missing)
    except Exception:
        return ()


def _is_allowed(citation: str, allowed: Sequence[str]) -> bool:
    for entry in allowed:
        entry = _text(entry)
        if not entry:
            continue
        if citation == entry or citation.endswith("/" + entry) or entry.endswith("/" + citation):
            return True
    return False


def unknown_sources(answer: str, allowed: Sequence[str]) -> tuple[str, ...]:
    """The .md files cited in answer that match none of allowed."""
    try:
        entries = tuple(allowed or ())
        unknown: list[str] = []
        for match in _CITATION_RE.finditer(_text(answer)):
            citation = match.group(0)
            if citation not in unknown and not _is_allowed(citation, entries):
                unknown.append(citation)
        return tuple(unknown)
    except Exception:
        return ()

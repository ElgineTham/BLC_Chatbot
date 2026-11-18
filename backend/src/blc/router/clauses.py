"""Cutting a question into parts and spotting follow-ups, using only the user's words (spec 013 4.1, 4.2)."""

from __future__ import annotations

import re

QUESTION_STARTERS: tuple[str, ...] = (
    "how", "what", "where", "which", "when", "who", "whom", "whose", "why",
    "do", "does", "did", "is", "are", "can", "could", "should", "would", "will", "may",
)
FOLLOW_UP_LEADS: tuple[str, ...] = ("and", "also", "so", "then")
FOLLOW_UP_PREFIXES: tuple[str, ...] = ("what about", "how about")

_STARTERS = "|".join(QUESTION_STARTERS)
_STARTS_WITH_STARTER = re.compile(rf"\s*(?:{_STARTERS})(?![a-z])", re.IGNORECASE)
_BOUNDARY = re.compile(
    r"\?(?=\s+\S)"
    r"|;"
    rf"|,?\s*\b(?:and\s+also|and|also)\b\s+(?=(?:{_STARTERS})(?![a-z]))",
    re.IGNORECASE,
)
_LEADING_CONNECTIVE = re.compile(r"^(?:and|also)\b\s*", re.IGNORECASE)
_WORD = re.compile(r"[a-z]+")


def _tidy(piece: str) -> str:
    piece = piece.strip(" \t\r\n,;")
    while True:
        stripped = _LEADING_CONNECTIVE.sub("", piece).strip(" \t\r\n,;")
        if stripped == piece:
            return piece
        piece = stripped


def split_clauses(question: str) -> tuple[str, ...]:
    """The question cut into parts at allowed boundaries only; () for blank text."""
    if not isinstance(question, str) or not question.strip():
        return ()
    pieces: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(question):
        text = match.group(0)
        if text == "?":
            cut, resume = match.end(), match.end()
        else:
            cut, resume = match.start(), match.end()
            if text != ";" and not _STARTS_WITH_STARTER.match(question, start, cut):
                continue
        pieces.append(question[start:cut])
        start = resume
    pieces.append(question[start:])
    return tuple(piece for piece in map(_tidy, pieces) if piece)


def _last_user_text(history: object) -> str | None:
    if not isinstance(history, (list, tuple)):
        return None
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def last_user_text(history: list[dict[str, str]]) -> str | None:
    """Content of the last user item of history that has text, else None."""
    return _last_user_text(history)


def is_follow_up(history: list[dict[str, str]], question: str) -> bool:
    """True if question answers or extends the user's previous message (spec 013 4.2)."""
    if not isinstance(question, str) or not question.strip():
        return False
    if _last_user_text(history) is None:
        return False
    text = question.strip().lower()
    while True:
        head = _WORD.match(text)
        if head and head.group(0) in FOLLOW_UP_LEADS:
            text = text[head.end():].lstrip(" ,")
        else:
            break
    if text.startswith(FOLLOW_UP_PREFIXES):
        return True
    return not any(word in QUESTION_STARTERS for word in _WORD.findall(text))

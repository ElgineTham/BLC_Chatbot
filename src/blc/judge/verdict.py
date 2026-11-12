"""The judge's verdict and how a model reply is read as one."""

from __future__ import annotations

import re
from dataclasses import dataclass

STRIP_CHARS = "*#:.- \t\r\n"
PASS_WORD = "PASS"
FAIL_WORD = "FAIL"
_FIRST_WORD = re.compile(r"[A-Za-z]+")


class JudgeError(Exception):
    """The judge model's reply could not be read as a verdict."""


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str


def reply_text(content: object) -> str:
    """Text of a chat model reply's content (a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


def parse_verdict(reply: str) -> Verdict:
    """Read `PASS` / `FAIL` plus an optional reason from the start of a reply."""
    text = reply.lstrip(STRIP_CHARS)
    match = _FIRST_WORD.match(text)
    word = match.group(0).upper() if match else ""
    if word not in (PASS_WORD, FAIL_WORD):
        raise JudgeError(f"Judge reply does not start with PASS or FAIL: {reply!r}")
    reason = text[match.end():].strip(STRIP_CHARS)
    return Verdict(passed=word == PASS_WORD, reason=reason)

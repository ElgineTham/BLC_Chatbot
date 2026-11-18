"""Validation of POST /api/chat request bodies."""

from __future__ import annotations

from typing import Any

MAX_QUESTION_CHARS = 2000
ALLOWED_ROLES = ("user", "assistant", "summary")
ERROR_MESSAGE = "Sorry, something went wrong on my end. Please try again."


class BadRequest(ValueError):
    """The request body is not acceptable; the message is safe to show."""


def parse_chat_request(body: Any) -> tuple[str, list[dict[str, str]]]:
    """Return (stripped question, history exactly as sent) or raise BadRequest."""
    if not isinstance(body, dict):
        raise BadRequest("Request body must be a JSON object.")
    question = body.get("question")
    if not isinstance(question, str) or not question.strip():
        raise BadRequest("question must be a non-empty string.")
    question = question.strip()
    if len(question) > MAX_QUESTION_CHARS:
        raise BadRequest(f"question is longer than {MAX_QUESTION_CHARS} characters.")
    history = body.get("history", [])
    if not isinstance(history, list):
        raise BadRequest("history must be a list.")
    for item in history:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("role"), str)
            or not isinstance(item.get("content"), str)
        ):
            raise BadRequest("history items need a string role and content.")
        if item["role"] not in ALLOWED_ROLES:
            raise BadRequest("history item has an unknown role.")
    return question, history

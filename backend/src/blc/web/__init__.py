"""Web chat backend (spec 032): FastAPI app that streams the planned flow's answer."""

from __future__ import annotations

from blc.web.answerer import Answerer, ChatTurn, build_answerer
from blc.web.app import LOGO_URL, MANIFEST_URL, create_app
from blc.web.requests import ALLOWED_ROLES, ERROR_MESSAGE, MAX_QUESTION_CHARS

__all__ = [
    "Answerer", "ChatTurn", "build_answerer", "create_app", "LOGO_URL", "MANIFEST_URL",
    "ALLOWED_ROLES", "ERROR_MESSAGE", "MAX_QUESTION_CHARS",
]

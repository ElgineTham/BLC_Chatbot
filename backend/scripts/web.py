"""Web chat entry point (spec 032): serves the chat page and the streaming API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from blc.web import (  # noqa: E402
    ALLOWED_ROLES,
    ERROR_MESSAGE,
    LOGO_URL,
    MANIFEST_URL,
    MAX_QUESTION_CHARS,
    Answerer,
    ChatTurn,
    build_answerer,
    create_app,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

__all__ = [
    "ALLOWED_ROLES", "ERROR_MESSAGE", "LOGO_URL", "MANIFEST_URL", "MAX_QUESTION_CHARS",
    "Answerer", "ChatTurn", "build_answerer", "create_app", "main",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bay Laurel Catering web chat")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    import chat  # heavy imports (LangChain, Chroma) only when serving

    started = chat.start_stack()
    if started is None:
        return 1
    llm, store = started

    import uvicorn

    try:
        drink_catalog = chat.load_catalog()
    except (chat.RuleFileError, OSError):
        drink_catalog = None
    app = create_app(build_answerer(llm, store, drink_catalog))
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Turn one answerer call into an NDJSON stream."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from blc.web.answerer import Answerer
from blc.web.requests import ERROR_MESSAGE

_END = object()


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def stream_answer(
    answer: Answerer, question: str, history: list[dict[str, str]]
) -> Iterator[str]:
    """Yield token lines as they arrive, then one done or error line."""
    pieces: queue.Queue[Any] = queue.Queue()

    def work() -> None:
        try:
            turn = answer(question, history, lambda text: pieces.put(("token", text)))
            pieces.put(("done", turn))
        except Exception:  # noqa: BLE001 - never leak the exception text
            pieces.put(("error", None))
        finally:
            pieces.put(_END)

    threading.Thread(target=work, daemon=True).start()
    while (item := pieces.get()) is not _END:
        kind, value = item
        if kind == "token":
            yield _line({"type": "token", "text": value})
        elif kind == "done":
            yield _line({"type": "done", "reply": value.reply, "history": value.history})
        else:
            yield _line({"type": "error", "message": ERROR_MESSAGE})

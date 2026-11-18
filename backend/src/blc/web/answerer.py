"""The answerer: one chat turn through the planned flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from blc.flow import run_planned_turn
from blc.history import summarize_if_long


@dataclass(frozen=True)
class ChatTurn:
    reply: str
    history: list[dict[str, str]]


Answerer = Callable[[str, list[dict[str, str]], Callable[[str], None]], ChatTurn]


def build_answerer(llm: BaseChatModel, store, drink_catalog=None) -> Answerer:
    """The real answerer, as chat.py main() runs it."""
    def answer(
        question: str, history: list[dict[str, str]], on_token: Callable[[str], None]
    ) -> ChatTurn:
        outcome = run_planned_turn(
            llm,
            store,
            question,
            summarize_if_long(llm, history),
            on_token=on_token,
            drink_catalog=drink_catalog,
        )
        return ChatTurn(reply=outcome.reply, history=outcome.history)

    return answer

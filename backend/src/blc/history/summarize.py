"""Replace over-long history with one summary item."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

HISTORY_TOKEN_LIMIT = 2000
CHARS_PER_TOKEN = 4
SYSTEM_PROMPT = "You summarize workplace chat history accurately and briefly."
SUMMARIZE_PROMPT = """Summarize the following conversation for Bay Laurel Catering staff chat history.
Keep important facts: locations, quantities, recipes, procedures, and open questions.
Drop small talk. Be concise.


{conversation}
"""
ROLE_LABELS = {"summary": "Summary", "user": "User", "assistant": "Assistant"}


def count_tokens(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def history_tokens(history: list[dict[str, str]]) -> int:
    return sum(count_tokens(item["content"]) for item in history)


def format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(empty)"
    return "\n".join(
        f"{ROLE_LABELS.get(item['role'], item['role'])}: {item['content']}"
        for item in history
    )


def summarize_history(llm: BaseChatModel, history: list[dict[str, str]]) -> str:
    message = SUMMARIZE_PROMPT.format(conversation=format_history(history))
    response = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)]
    )
    return str(response.content).strip()


def summarize_if_long(
    llm: BaseChatModel, history: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Replace over-long history with one summary item. Prints nothing."""
    if history_tokens(history) <= HISTORY_TOKEN_LIMIT:
        return history
    return [{"role": "summary", "content": summarize_history(llm, history)}]

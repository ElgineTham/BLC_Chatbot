"""Helpers for the spec 034 tests. Put on sys.path by conftest.py."""
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = REPO_ROOT / "backend" / "src"


class FakeModel(BaseChatModel):
    """Records every call and returns a fixed AIMessage content."""

    reply: str = "SUMMARY"
    calls: List[Any] = []

    @property
    def _llm_type(self) -> str:
        return "fake-034"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.calls.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])


def make_long_history(limit: int):
    """User/assistant items whose total content is well over limit * 4 characters."""
    chunk = "word " * 200  # 1000 chars
    n = (limit * 4 * 3) // len(chunk) + 2
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"{i} {chunk}"}
        for i in range(n)
    ]

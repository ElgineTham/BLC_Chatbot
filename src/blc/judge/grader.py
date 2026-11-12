"""Grade a chatbot answer against a reference answer with an LLM."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from blc.judge.prompt import build_prompt
from blc.judge.verdict import Verdict, parse_verdict, reply_text

JUDGE_MODEL = "qwen2.5:14b"
EMPTY_ANSWER_REASON = "The answer is empty."


def _default_llm() -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(model=JUDGE_MODEL, temperature=0)


def judge_answer(
    question: str,
    reference: str,
    answer: str,
    llm: BaseChatModel | None = None,
) -> Verdict:
    """Grade `answer` to `question` against `reference`.

    Raises ValueError for a blank question or reference, JudgeError for an
    unreadable reply. A blank answer fails without calling the model.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    if not reference.strip():
        raise ValueError("reference must not be empty")
    if not answer.strip():
        return Verdict(False, EMPTY_ANSWER_REASON)
    model = llm if llm is not None else _default_llm()
    reply = model.invoke(build_prompt(question, reference, answer))
    return parse_verdict(reply_text(reply.content))

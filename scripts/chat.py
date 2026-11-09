"""Interactive RAG chat for Bay Laurel Catering knowledge."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings

ROOT = Path(__file__).resolve().parents[1]
CHROMA_DIR = ROOT / ".chroma"
COLLECTION_NAME = "blc_knowledge"
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "qwen2.5:7b"
TOP_K = 3
HISTORY_TOKEN_LIMIT = 2000
CHARS_PER_TOKEN = 4
EXIT_COMMANDS: frozenset[str] = frozenset({
    "bye", "bye bye", "goodbye", "good bye",
    "see you", "see ya", "see you later", "see you soon", "talk to you later",
    "quit", "exit", "stop", "im done", "thats all", "thats it",
    "take care", "good night", "goodnight", "have a good one",
})
EXIT_FILLERS: frozenset[str] = frozenset({
    "okay", "ok", "alright", "all right", "thanks", "thank you",
})
APOSTROPHES = ("'", "\u2019")

SYSTEM_PROMPT = """You are Bay Laurel Catering's internal assistant for employees.
Answer ONLY using the provided context.
If the context does not contain the answer, say you don't know and suggest rephrasing the question.
If there is no recipe for the asked food or drink, say you don't know how to make it.
If a related supply exists in the context, say where it is and cite the source path(s).
Do not invent a recipe from a supply or location document.
Keep answers short and practical for kitchen/beverage staff.
Always mention the source path(s) you used from the context."""

SUMMARIZE_PROMPT = """Summarize the following conversation for Bay Laurel Catering staff chat history.
Keep important facts: locations, quantities, recipes, procedures, and open questions.
Drop small talk. Be concise.


{conversation}
"""


def count_tokens(text: str) -> int:
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def history_tokens(history: list[dict[str, str]]) -> int:
    if not history:
        return 0
    return sum(count_tokens(item["content"]) for item in history)


def format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(empty)"

    lines: list[str] = []
    for item in history:
        role = item["role"]
        content = item["content"]
        if role == "summary":
            lines.append(f"Summary: {content}")
        elif role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
        else:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def format_context(docs: list[Document]) -> str:
    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        blocks.append(f"[{index}] ({source})\n{doc.page_content.strip()}")
    return "\n\n".join(blocks)


def build_store() -> Chroma:
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def retrieve(store: Chroma, question: str) -> list[Document]:
    return store.similarity_search(question, k=TOP_K)


def summarize_history(llm: ChatOllama, history: list[dict[str, str]]) -> str:
    conversation = format_history(history)
    message = SUMMARIZE_PROMPT.format(conversation=conversation)
    response = llm.invoke(
        [
            SystemMessage(
                content="You summarize workplace chat history accurately and briefly."
            ),
            HumanMessage(content=message),
        ]
    )
    return str(response.content).strip()


def maybe_summarize(
    llm: ChatOllama, history: list[dict[str, str]]
) -> list[dict[str, str]]:
    """If prior history exceeds the token limit, replace it with one summary item."""
    if history_tokens(history) <= HISTORY_TOKEN_LIMIT:
        return history

    print("(history over 2000 tokens — summarizing prior chat…)")
    summary = summarize_history(llm, history)
    return [{"role": "summary", "content": summary}]


def answer_from_context(
    llm: ChatOllama,
    history: list[dict[str, str]],
    docs: list[Document],
    question: str,
) -> str:
    prompt = f"""System: {SYSTEM_PROMPT}

Chat history:
{format_history(history)}

Context:
{format_context(docs)}

Question:
{question}

Answer:"""
    response = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
    )
    return str(response.content).strip()


def unknown_retrieval_reply() -> str:
    return (
        "I don't know based on the available Bay Laurel documents. "
        "Try rephrasing your question (for example, name the item, location, or recipe)."
    )


def normalize_utterance(text: str) -> str:
    """1. casefold.
    2. Delete apostrophes (' and U+2019 ’), so "that's" becomes "thats" and "I'm" becomes "im".
    3. Replace every other character that is not a letter, digit or whitespace with a space,
       so "bye-bye!" becomes "bye bye".
    4. Collapse whitespace runs to one space and strip.
    Returns "" for input with no letters or digits."""
    folded = text.casefold()
    for apostrophe in APOSTROPHES:
        folded = folded.replace(apostrophe, "")
    spaced = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in folded)
    return " ".join(spaced.split())


def _exit_entry_lengths() -> tuple[int, ...]:
    """Distinct word counts of all exit entries, longest first."""
    entries = EXIT_COMMANDS | EXIT_FILLERS
    return tuple(sorted({len(entry.split()) for entry in entries}, reverse=True))


def is_exit_utterance(text: str) -> bool:
    """Split normalize_utterance(text) into words. Return True iff
    (a) there is at least one word,
    (b) the words can be split, front to back, into consecutive items, each of which is a
        whole entry of EXIT_COMMANDS or EXIT_FILLERS (multi-word entries match consecutive
        words; entries may repeat and appear in any order), and
    (c) at least one item is from EXIT_COMMANDS.
    If several splits exist, any valid split that meets (c) counts."""
    words = normalize_utterance(text).split()
    if not words:
        return False
    lengths = _exit_entry_lengths()
    n = len(words)
    # reach[i] = set of "has a command been used" flags for valid splits of words[:i].
    reach: list[set[bool]] = [set() for _ in range(n + 1)]
    reach[0].add(False)
    for start in range(n):
        if not reach[start]:
            continue
        for length in lengths:
            end = start + length
            if end > n:
                continue
            item = " ".join(words[start:end])
            if item in EXIT_COMMANDS:
                reach[end].add(True)
            elif item in EXIT_FILLERS:
                reach[end].update(reach[start])
    return True in reach[n]


@dataclass(frozen=True)
class TurnResult:
    reply: str  # the assistant's answer, exactly as printed
    history: list[dict[str, str]]  # new history after this turn
    docs: list[Document]  # docs returned by retrieve(); [] if none


def answer_turn(
    store: Chroma,
    llm: ChatOllama,
    history: list[dict[str, str]],
    question: str,
) -> TurnResult:
    """Run one question through the RAG pipeline.

    Raises ValueError if question is empty or whitespace-only (before any
    store or llm call).
    """
    q = question.strip()
    if q == "":
        raise ValueError("question must not be empty or whitespace-only")

    # Summarize only prior history (exclude the current question).
    prior = maybe_summarize(llm, history)

    docs = retrieve(store, q)
    if not docs:
        docs = []
        reply = unknown_retrieval_reply()
    else:
        reply = answer_from_context(llm, prior, docs, q)

    new_history = list(prior) + [
        {"role": "user", "content": q},
        {"role": "assistant", "content": reply},
    ]
    return TurnResult(reply=reply, history=new_history, docs=docs)


def main() -> int:
    if not CHROMA_DIR.exists():
        print(
            f"Chroma store not found at {CHROMA_DIR}. Run scripts/ingest.py first.",
            file=sys.stderr,
        )
        return 1

    store = build_store()
    llm = ChatOllama(model=CHAT_MODEL, temperature=0.1)
    history: list[dict[str, str]] = []

    print("Bay Laurel Catering chatbot")
    print("Type quit, exit, or bye to leave.\n")

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not raw:
            continue

        if is_exit_utterance(raw):
            print("Bye.")
            return 0

        result = answer_turn(store, llm, history, raw)
        print(f"Assistant: {result.reply}\n")
        history = result.history


if __name__ == "__main__":
    raise SystemExit(main())

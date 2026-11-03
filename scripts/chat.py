"""Interactive RAG chat for Bay Laurel Catering knowledge."""

from __future__ import annotations

import sys
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
EXIT_COMMANDS = {"quit", "exit", "bye"}

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

        if raw.casefold() in EXIT_COMMANDS:
            print("Bye.")
            return 0

        # Summarize only prior history (exclude the current question).
        history = maybe_summarize(llm, history)

        docs = retrieve(store, raw)
        if not docs:
            reply = unknown_retrieval_reply()
            print(f"Assistant: {reply}\n")
            history.append({"role": "user", "content": raw})
            history.append({"role": "assistant", "content": reply})
            continue

        reply = answer_from_context(llm, history, docs, raw)
        print(f"Assistant: {reply}\n")

        history.append({"role": "user", "content": raw})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    raise SystemExit(main())

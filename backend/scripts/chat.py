"""Interactive RAG chat for Bay Laurel Catering knowledge."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from blc.flow import run_planned_turn  # noqa: E402
from blc.history import HISTORY_TOKEN_LIMIT, summarize_if_long  # noqa: E402,F401
from blc.ingest import StoreModelMismatchError, check_store_model  # noqa: E402,F401
from blc.llm import (  # noqa: E402
    CHAT_API_KEY_ENV,  # noqa: F401
    CHAT_MODEL,  # noqa: F401
    EMBED_MODEL,  # noqa: F401
    MissingApiKeyError,
    build_chat_model,
    build_embeddings,
)
from blc.pull_sheet import RuleFileError, load_catalog  # noqa: E402
from blc.retrieval import DomainStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = ROOT / ".chroma"
COLLECTION_NAME = "blc_knowledge"
TOP_K = 3

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
CHAT_TEMPERATURE = 0


def build_store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=build_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def build_domain_store() -> DomainStore:
    return DomainStore(build_store())


def retrieve(store: Chroma, question: str) -> list[Document]:
    return store.similarity_search(question, k=TOP_K)


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

def start_stack(
    make_store=None, temperature: float | None = None
) -> tuple[BaseChatModel, object] | None:
    """Load .env, build the chat model and the store, and check the store was built by
    EMBED_MODEL. On any startup problem print the message to stderr and return None."""
    load_dotenv()
    make_store = build_domain_store if make_store is None else make_store
    temperature = CHAT_TEMPERATURE if temperature is None else temperature
    try:
        llm = build_chat_model(temperature=temperature)
        build_embeddings()  # fail on a missing key before touching the store
        if not CHROMA_DIR.exists():
            print(
                f"Chroma store not found at {CHROMA_DIR}. Run scripts/ingest.py first.",
                file=sys.stderr,
            )
            return None
        store = make_store()
        check_store_model(getattr(store, "_store", store))
    except (MissingApiKeyError, StoreModelMismatchError) as exc:
        print(str(exc), file=sys.stderr)
        return None
    return llm, store


def main() -> int:
    started = start_stack()
    if started is None:
        return 1
    llm, store = started
    try:
        drink_catalog = load_catalog()
    except (RuleFileError, OSError):
        drink_catalog = None
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

        print("Assistant: ", end="", flush=True)
        outcome = run_planned_turn(
            llm,
            store,
            raw,
            summarize_if_long(llm, history),
            on_token=lambda piece: print(piece, end="", flush=True),
            drink_catalog=drink_catalog,
        )
        print("\n")
        history = outcome.history


if __name__ == "__main__":
    raise SystemExit(main())

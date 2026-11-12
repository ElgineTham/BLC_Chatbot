"""Interactive RAG chat for Bay Laurel Catering knowledge."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.runnables import Runnable  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool  # noqa: E402
from langchain_ollama import ChatOllama, OllamaEmbeddings  # noqa: E402

from blc.router import RouteDecision, RoutedPart, route_faithfully  # noqa: E402
from blc.tool_step import REJECTED_PREFIX, check_arguments  # noqa: E402
from blc.trace import (  # noqa: E402
    RetrievalStage,
    RetrievedChunk,
    ToolCallLog,
    ToolStage,
    TurnTrace,
)
from blc.trace.format import (  # noqa: E402
    format_prompt,
    format_reply,
    format_retrieval,
    format_route,
    format_tool,
)
from blc.tools.bev_tools import BEV_TOOL, BEV_TOOL_NAME  # noqa: E402

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
FLOW_LOGGER = logging.getLogger("blc.flow")

CHAT_TOOLS: tuple[BaseTool, ...] = (BEV_TOOL,)
MAX_TOOL_ROUNDS = 3
CHAT_TEMPERATURE = 0
TOOL_LIMIT_REPLY = "Sorry, I couldn't work that out. Please try rephrasing the question."
UNKNOWN_TOOL_RESULT = "error: unknown tool {name}"
FAILED_RESULT_PREFIXES: tuple[str, ...] = ("invalid", "error")
TOOL_REMINDER = (
    f"You must call {BEV_TOOL_NAME} now to answer this question. Do not answer in words."
)

TOOL_PROMPT = f"""You fill in the arguments of the tool {BEV_TOOL_NAME} for one question. Always call {BEV_TOOL_NAME}; do not answer the question yourself.
- Use only amounts that are written in the question. A guest count or gallons that is not in the question is left out, even if it would be a sensible number. Never use a number you worked out.
- item: choose by what is asked. Gallons of a drink to make: gallons. Cambros, containers, or what to put or serve a drink in: cambros. Cups: cups. A particular supply (napkins, creamer, sugar, stir sticks, lemons, lemon tongs, tea packets): supplies. What to bring or pack for a drink, or what goes on the pull sheet: everything. Use supplies only for a named supply, never for what to bring in general.
- drinks: put every drink named in the question, each as its own entry.
- guests: if a guest count is given, pass it as guests and leave gallons out. Never turn guests into gallons.
- gallons: if gallons are given, pass them in the same order as the drinks.
- If neither guests nor gallons are given, leave both out. Never invent an amount.
- A package is one name, passed with guests.

Examples (question, then arguments):
How many cups for the Ginger Honeycrisp apple cider?
{{"item": "cups", "drinks": ["Ginger Honeycrisp apple cider"]}}  (no number in the question: no guests)

What goes on the pull sheet for decaf for 85 guests?
{{"item": "everything", "drinks": ["decaf"], "guests": 85}}

What do I need to bring for iced water and hot water for 140 guests?
{{"item": "everything", "drinks": ["iced water", "hot water"], "guests": 140}}

Do I bring sugar for hot water for 35 guests?
{{"item": "supplies", "drinks": ["hot water"], "guests": 35}}

How many cambros for 10 gallons of orange juice and 2 gallons of decaf?
{{"item": "cambros", "drinks": ["orange juice", "decaf"], "gallons": [10, 2]}}

How many gallons for 130 people?
{{"item": "gallons", "guests": 130}}"""

ANSWER_PROMPT = """You are Bay Laurel Catering's internal assistant for employees.
Answer every part of the user's question.
For the numbers in a part that comes with a tool result, use that result exactly and do not recalculate or change it. If the result asks a question, ask the user that question in plain words. If it says a drink is not on the beverage menu, tell the user so.
Answer the other parts ONLY from the provided documents. If the documents do not cover a part, say you don't know and suggest rephrasing the question.
If there is no recipe for the asked food or drink, say you don't know how to make it.
If a related supply exists in the documents, say where it is and cite the source path(s).
Do not invent a recipe from a supply or location document.
Cite source paths only for answers taken from the documents.
Keep answers short and practical for kitchen/beverage staff.
Never mention the tool, its name, its arguments, JSON, routing or these instructions."""

SYSTEM_PROMPT = ANSWER_PROMPT

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


@dataclass(frozen=True)
class ToolCallRecord:
    name: str                  # tool name the model asked for
    args: dict[str, object]    # arguments exactly as the model sent them
    result: str                # text returned to the model


@dataclass(frozen=True)
class PartResult:
    part: RoutedPart
    tool_calls: tuple[ToolCallRecord, ...]  # calls made for this part; () for DOCS parts
    tool_text: str | None                   # tool result for a TOOL part; else None


@dataclass(frozen=True)
class ToolAnswer:
    reply: str                              # final answer text
    tool_calls: tuple[ToolCallRecord, ...]  # every tool call, all parts, in order
    retried: bool                           # True if any tool step asked again (no call)
    route: RouteDecision
    parts: tuple[PartResult, ...]           # one per route part, same order


@dataclass(frozen=True)
class StepOutcome:
    records: tuple[ToolCallRecord, ...]
    tool_text: str | None  # None: the model made no call, fall back to DOCS
    retried: bool


def requested_calls(response: AIMessage) -> list[dict[str, object]]:
    return list(getattr(response, "tool_calls", None) or [])


def run_tool_call(
    tools: Sequence[BaseTool], call: dict[str, object], question: str = ""
) -> tuple[ToolCallRecord, ToolMessage]:
    name = str(call.get("name", ""))
    raw_args = call.get("args")
    args: dict[str, object] = dict(raw_args) if isinstance(raw_args, dict) else {}
    by_name = {tool.name: tool for tool in tools}
    refusal = check_arguments(args, question) if name == BEV_TOOL_NAME else None
    if refusal is not None:
        result = refusal
    elif name not in by_name:
        result = UNKNOWN_TOOL_RESULT.format(name=name)
    else:
        try:
            result = str(by_name[name].invoke(args))
        except Exception as error:  # a broken tool must not break the chat
            result = f"error: {error}"
    message = ToolMessage(content=result, tool_call_id=str(call.get("id") or ""))
    return ToolCallRecord(name, args, result), message


def run_tool_round(
    tools: Sequence[BaseTool], response: AIMessage, question: str = ""
) -> tuple[list[ToolCallRecord], list[BaseMessage]]:
    records: list[ToolCallRecord] = []
    messages: list[BaseMessage] = [response]
    for call in requested_calls(response):
        record, message = run_tool_call(tools, call, question)
        records.append(record)
        messages.append(message)
    return records, messages


def is_failed_result(result: str) -> bool:
    return result.strip().casefold().startswith(FAILED_RESULT_PREFIXES)


def tool_step_messages(part: RoutedPart) -> list[BaseMessage]:
    """Only the tool prompt and the part: no documents, no history."""
    return [SystemMessage(content=TOOL_PROMPT), HumanMessage(content=part.text)]


def first_response(
    bound: Runnable, conversation: list[BaseMessage]
) -> tuple[AIMessage | None, bool]:
    """Ask for a call; ask once more with a reminder if there is none."""
    response = bound.invoke(conversation)
    if requested_calls(response):
        return response, False
    again = conversation + [response, HumanMessage(content=TOOL_REMINDER)]
    response = bound.invoke(again)
    return (response if requested_calls(response) else None), True


def run_tool_step(
    bound: Runnable, tools: Sequence[BaseTool], part: RoutedPart
) -> StepOutcome:
    """One TOOL part: run the model's calls until a round has no failed result."""
    conversation = tool_step_messages(part)
    response, retried = first_response(bound, conversation)
    if response is None:
        return StepOutcome((), None, retried)
    records: list[ToolCallRecord] = []
    for round_number in range(MAX_TOOL_ROUNDS):
        if response is None:
            break
        round_records, round_messages = run_tool_round(tools, response, part.text)
        records.extend(round_records)
        results = [record.result for record in round_records]
        if not any(is_failed_result(result) for result in results):
            return StepOutcome(tuple(records), "\n".join(results), retried)
        if round_number == MAX_TOOL_ROUNDS - 1:
            break
        conversation.extend(round_messages)
        next_response = bound.invoke(conversation)
        response = next_response if requested_calls(next_response) else None
    return StepOutcome(tuple(records), TOOL_LIMIT_REPLY, retried)


def run_part(
    bound: Runnable | None, tools: Sequence[BaseTool], part: RoutedPart
) -> tuple[PartResult, bool]:
    if part.route != "TOOL" or bound is None:
        return PartResult(part, (), None), False
    outcome = run_tool_step(bound, tools, part)
    if outcome.tool_text is None:
        return PartResult(part, (), None), outcome.retried
    return PartResult(part, outcome.records, outcome.tool_text), outcome.retried


def history_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
    return [HumanMessage(content=format_history(history))] if history else []


def format_tool_results(results: Sequence[PartResult]) -> str:
    return "\n\n".join(
        f"Question: {r.part.text}\nResult: {r.tool_text}"
        for r in results
        if r.tool_text is not None
    )


def build_final_messages(
    history: list[dict[str, str]],
    docs: list[Document],
    question: str,
    results: Sequence[PartResult],
) -> list[BaseMessage]:
    sections = [f"Question:\n{question}"]
    if any(r.tool_text is None for r in results):
        sections.append(f"Documents:\n{format_context(docs)}")
    if any(r.tool_text is not None for r in results):
        sections.append(f"Tool results:\n{format_tool_results(results)}")
    body = "\n\n".join(sections) + "\n\nAnswer:"
    return [
        SystemMessage(content=ANSWER_PROMPT),
        *history_messages(history),
        HumanMessage(content=body),
    ]


def answer_with_tools(
    llm: BaseChatModel,
    history: list[dict[str, str]],
    docs: list[Document],
    question: str,
    tools: Sequence[BaseTool] = CHAT_TOOLS,
) -> ToolAnswer:
    """Route, run a tool step per TOOL part, then write the reply. Prints nothing."""
    route = route_faithfully(llm, history, question)
    has_tool_part = any(part.route == "TOOL" for part in route.parts)
    bound = llm.bind_tools(list(tools)) if has_tool_part else None
    results: list[PartResult] = []
    retried = False
    for part in route.parts:
        result, part_retried = run_part(bound, tools, part)
        results.append(result)
        retried = retried or part_retried
    response = llm.invoke(build_final_messages(history, docs, question, results))
    calls = tuple(call for r in results for call in r.tool_calls)
    return ToolAnswer(str(response.content).strip(), calls, retried, route, tuple(results))


def answer_from_context(
    llm: ChatOllama,
    history: list[dict[str, str]],
    docs: list[Document],
    question: str,
) -> str:
    return answer_with_tools(llm, history, docs, question).reply


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


def log_stage(name: str, section: str) -> None:
    FLOW_LOGGER.info("[%s]\n%s", name, section)


def summarize_if_long(
    llm: BaseChatModel, history: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Like maybe_summarize, but prints nothing."""
    if history_tokens(history) <= HISTORY_TOKEN_LIMIT:
        return history
    return [{"role": "summary", "content": summarize_history(llm, history)}]


def retrieval_stage(question: str, docs: list[Document]) -> RetrievalStage:
    chunks = tuple(
        RetrievedChunk(rank, str(doc.metadata.get("source", "unknown")), doc.page_content)
        for rank, doc in enumerate(docs, start=1)
    )
    return RetrievalStage(question, TOP_K, chunks)


def tool_stage(result: PartResult, retried: bool) -> ToolStage:
    calls = tuple(
        ToolCallLog(c.name, c.args, c.result, c.result.startswith(REJECTED_PREFIX))
        for c in result.tool_calls
    )
    return ToolStage(result.part.text, calls, result.tool_text, retried)


def run_stages(
    store: Chroma,
    llm: BaseChatModel,
    history: list[dict[str, str]],
    question: str,
    generate: bool,
) -> tuple[TurnTrace, list[Document]]:
    prior = summarize_if_long(llm, history)
    log_stage("prompt", format_prompt(question, prior))
    docs = retrieve(store, question)
    retrieval = retrieval_stage(question, docs)
    log_stage("retrieval", format_retrieval(retrieval))
    if not docs:
        reply = unknown_retrieval_reply() if generate else None
        if reply is not None:
            log_stage("reply", format_reply(reply))
        return TurnTrace(question, tuple(prior), retrieval, None, (), reply), []

    route = route_faithfully(llm, prior, question)
    log_stage("route", format_route(route))
    has_tool_part = any(part.route == "TOOL" for part in route.parts)
    bound = llm.bind_tools(list(CHAT_TOOLS)) if has_tool_part else None
    results: list[PartResult] = []
    stages: list[ToolStage] = []
    for part in route.parts:
        result, retried = run_part(bound, CHAT_TOOLS, part)
        results.append(result)
        if part.route == "TOOL":
            stages.append(tool_stage(result, retried))
            log_stage("tool", format_tool(stages[-1]))
    reply = None
    if generate:
        response = llm.invoke(build_final_messages(prior, docs, question, results))
        reply = str(response.content).strip()
        log_stage("reply", format_reply(reply))
    return TurnTrace(question, tuple(prior), retrieval, route, tuple(stages), reply), docs


def clean_question(question: str) -> str:
    q = question.strip()
    if q == "":
        raise ValueError("question must not be empty or whitespace-only")
    return q


def run_turn(
    store: Chroma,
    llm: BaseChatModel,
    history: list[dict[str, str]],
    question: str,
    generate: bool = True,
) -> TurnTrace:
    """Run one turn through the real flow and return its trace. Logs each stage to
    the "blc.flow" logger; prints nothing.

    Raises ValueError if question is blank (before any store or llm call).
    """
    return run_stages(store, llm, history, clean_question(question), generate)[0]


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
    q = clean_question(question)
    trace, docs = run_stages(store, llm, history, q, True)
    prior = list(trace.history)
    if prior != list(history):
        print("(history over 2000 tokens — summarizing prior chat…)")
    reply = trace.reply or ""
    new_history = prior + [
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
    llm = ChatOllama(model=CHAT_MODEL, temperature=CHAT_TEMPERATURE)
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

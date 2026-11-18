"""The stage records that make up a turn trace (spec 011)."""

from __future__ import annotations

from dataclasses import dataclass

from blc.router import RouteDecision

STAGE_NAMES: tuple[str, ...] = ("prompt", "route", "retrieval", "tool", "reply")


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int      # 1-based position in the retrieval result
    source: str    # the chunk's metadata "source"; "unknown" if missing
    text: str      # the chunk's page content


@dataclass(frozen=True)
class RetrievalStage:
    query: str                           # the text searched
    k: int                               # how many chunks were asked for
    chunks: tuple[RetrievedChunk, ...]   # in rank order; () if nothing was found


@dataclass(frozen=True)
class ToolCallLog:
    name: str                  # tool name the model asked for
    args: dict[str, object]    # arguments exactly as the model sent them
    result: str                # text returned to the model
    refused: bool              # True if the argument check refused the call (spec 009)


@dataclass(frozen=True)
class ToolStage:                         # one per TOOL part of the route, in order
    part: str                            # the TOOL part's text
    calls: tuple[ToolCallLog, ...]       # every call made for this part, in order
    tool_text: str | None                # the text used for the answer; None if fell back
    retried: bool                        # the model was asked again because it made no call


@dataclass(frozen=True)
class TurnTrace:
    question: str                                # the question as run (stripped)
    history: tuple[dict[str, str], ...]          # the history the flow used
    retrieval: RetrievalStage | None             # None if retrieval was not run
    route: RouteDecision | None                  # None if the router was not run
    tools: tuple[ToolStage, ...]                 # one per TOOL part; () if none
    reply: str | None                            # the final reply; None if not generated

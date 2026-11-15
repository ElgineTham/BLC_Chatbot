"""The LangGraph flow: plan -> run -> reply, and run_planned_turn (spec 019)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from blc.flow.invented import RejectedCall
from blc.flow.reply import build_answer_messages, passthrough_reply, stream_answer
from blc.flow.retry import check_plan
from blc.flow.run import DocumentStore, SearchResult, ToolResult, dedupe_documents, run_plan
from blc.flow.tool_runners import DEFAULT_TOOL_RUNNERS, ToolRunner
from blc.planner import Plan, plan_question

FLOW_NODES: tuple[str, ...] = ("plan", "run", "reply")
EMPTY_QUESTION_MESSAGE = "question must not be empty"


class FlowState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    plan: Plan
    first_plan: Plan
    rejected: tuple[RejectedCall, ...]
    retried: bool
    searches: tuple[SearchResult, ...]
    tools: tuple[ToolResult, ...]
    documents: tuple[Document, ...]
    reply: str
    answered_by_model: bool


@dataclass(frozen=True)
class TurnOutcome:
    question: str
    plan: Plan
    searches: tuple[SearchResult, ...]
    tools: tuple[ToolResult, ...]
    documents: tuple[Document, ...]
    reply: str
    answered_by_model: bool
    history: list[dict[str, str]]
    first_plan: Plan
    rejected: tuple[RejectedCall, ...]
    retried: bool


def build_flow_graph(
    llm: BaseChatModel,
    store: DocumentStore,
    planner_llm: BaseChatModel | None = None,
    tool_runners: Mapping[str, ToolRunner] | None = None,
):
    """The compiled graph. on_token is read from config["configurable"]["on_token"]."""
    planner = planner_llm or llm
    runners = DEFAULT_TOOL_RUNNERS if tool_runners is None else tool_runners

    def plan_node(state: FlowState) -> FlowState:
        question, history = state["question"], state["history"]
        checked = check_plan(planner, question, history, plan_question(planner, question, history))
        return {
            "plan": checked.plan, "first_plan": checked.first_plan,
            "rejected": checked.rejected, "retried": checked.retried,
        }

    def run_node(state: FlowState) -> FlowState:
        searches, tools = run_plan(state["plan"], store, runners)
        return {"searches": searches, "tools": tools, "documents": dedupe_documents(searches)}

    def reply_node(state: FlowState, config: RunnableConfig) -> FlowState:
        on_token: Callable[[str], None] | None = config.get("configurable", {}).get("on_token")
        fixed = passthrough_reply(state["searches"], state["tools"])
        if fixed is not None:
            if on_token is not None:
                on_token(fixed)
            return {"reply": fixed.strip(), "answered_by_model": False}
        messages = build_answer_messages(
            state["question"], state["history"], state["tools"], state["documents"]
        )
        return {"reply": stream_answer(llm, messages, on_token).strip(), "answered_by_model": True}

    graph = StateGraph(FlowState)
    graph.add_node("plan", plan_node)
    graph.add_node("run", run_node)
    graph.add_node("reply", reply_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "run")
    graph.add_edge("run", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


def run_planned_turn(
    llm: BaseChatModel,
    store: DocumentStore,
    question: str,
    history: list[dict[str, str]] | None = None,
    on_token: Callable[[str], None] | None = None,
    planner_llm: BaseChatModel | None = None,
    tool_runners: Mapping[str, ToolRunner] | None = None,
) -> TurnOutcome:
    """Plan, run and answer one question. Raises ValueError for an empty question."""
    question = question.strip()
    if not question:
        raise ValueError(EMPTY_QUESTION_MESSAGE)
    past = list(history or [])
    graph = build_flow_graph(llm, store, planner_llm, tool_runners)
    state = graph.invoke(
        {"question": question, "history": past},
        config={"configurable": {"on_token": on_token}},
    )
    reply = state["reply"]
    new_history = past + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": reply},
    ]
    return TurnOutcome(
        question=question,
        plan=state["plan"],
        searches=state["searches"],
        tools=state["tools"],
        documents=state["documents"],
        reply=reply,
        answered_by_model=state["answered_by_model"],
        history=new_history,
        first_plan=state["first_plan"],
        rejected=state["rejected"],
        retried=state["retried"],
    )

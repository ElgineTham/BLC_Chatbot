"""Spec 019, AC-4 (contract details): EC-11 to EC-15, NFR-1 (graph) and NFR-6 (prompt).

Unit: scripted fakes, no Ollama, nothing read under data/.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

import blc.flow as flow_pkg
from blc.flow import (DEFAULT_TOOL_RUNNERS, FLOW_ANSWER_PROMPT, FLOW_NODES, TOP_K,
                      build_flow_graph, run_planned_turn)

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"

HISTORY = [
    {"role": "user", "content": "How many cambros for coffee and decaf?"},
    {"role": "assistant", "content": "How many gallons of each drink, or how many guests?"},
]


# ---------------------------------------------------------------- EC-11 empty question

@pytest.mark.parametrize("question", ["", "   ", "\n", "\t \n"])
def test_empty_question_raises_before_any_call(question, make_llm, make_store, make_runner, mk):
    """Covers: AC-4 (wrong), EC-11, EC-11 (boundary). Empty or whitespace-only question -> ValueError;
    no model, store or runner is called."""
    llm = make_llm(plan_reply=mk.ai((SEARCH, {"query": "x"})), pieces=("a",))
    planner = make_llm(plan_reply=mk.ai((SEARCH, {"query": "x"})))
    store = make_store({"x": []})
    runners = {BEV: make_runner(), REC: make_runner()}
    with pytest.raises(ValueError):
        run_planned_turn(llm, store, question, [], planner_llm=planner, tool_runners=runners)
    assert llm.bind_calls == [] and llm.invoke_calls == [] and llm.stream_calls == []
    assert planner.bind_calls == [] and planner.invoke_calls == []
    assert store.calls == []
    assert runners[BEV].calls == [] and runners[REC].calls == []


def test_one_character_question_is_accepted(run):
    """Covers: AC-4 (boundary), EC-11. The shortest non-blank question runs."""
    r = run("?", [(SEARCH, {"query": "x"})])
    assert r.outcome.question == "?"


# ---------------------------------------------------------------- EC-12 history

def test_summary_history_item_reaches_the_messages(run, text_of):
    """Covers: AC-4 (right), EC-12. A summary item's content appears in the planner and answer messages."""
    hist = [{"role": "summary", "content": "Earlier they asked about iced tea cambros."}] + HISTORY
    r = run("5 gallons each.", [(SEARCH, {"query": "x"})], history=hist,
            docs={"x": []}, pieces=("a",))
    # empty search + no tool -> no answer call; planner still saw the summary
    assert "Earlier they asked about iced tea cambros." in text_of(r.llm.invoke_calls[0])


def test_summary_history_item_reaches_the_answer_messages(run, doc, text_of):
    """Covers: AC-4 (right), EC-12. A summary item's content appears in the answer messages."""
    hist = [{"role": "summary", "content": "Earlier they asked about iced tea cambros."}]
    r = run("Where?", [(SEARCH, {"query": "x"})], history=hist, docs={"x": [doc("Doc.", "data/a.md")]})
    assert "Earlier they asked about iced tea cambros." in text_of(r.llm.stream_calls[0])


# ---------------------------------------------------------------- EC-13 planner_llm

def test_separate_planner_binds_tools_and_answer_model_streams(run, doc):
    """Covers: AC-4 (right), EC-13. With planner_llm: bind_tools only on it; stream only on llm."""
    r = run("q", [(SEARCH, {"query": "x"})], docs={"x": [doc("Doc.", "data/a.md")]},
            separate_planner=True)
    assert len(r.planner.bind_calls) == 1
    assert len(r.planner.invoke_calls) == 1
    assert r.planner.stream_calls == []
    assert r.llm.bind_calls == [] and r.llm.invoke_calls == []
    assert len(r.llm.stream_calls) == 1


def test_without_planner_llm_one_model_does_both(run, doc):
    """Covers: AC-4 (right), EC-13. Without planner_llm, llm gets bind_tools once, and stream."""
    r = run("q", [(SEARCH, {"query": "x"})], docs={"x": [doc("Doc.", "data/a.md")]})
    assert len(r.llm.bind_calls) == 1
    assert len(r.llm.invoke_calls) == 1
    assert len(r.llm.stream_calls) == 1


def test_separate_planner_still_plans_when_no_answer_is_needed(run):
    """Covers: AC-4 (boundary), EC-13. NO_DOCS_REPLY turn: the planner was used once, llm never."""
    r = run("q", [(SEARCH, {"query": "x"})], docs={}, separate_planner=True)
    assert len(r.planner.invoke_calls) == 1
    assert r.llm.stream_calls == [] and r.llm.bind_calls == []


# ---------------------------------------------------------------- EC-14 prompt and graph

def test_flow_answer_prompt_is_first_message_of_the_answer_call(run, doc):
    """Covers: AC-4 (right), EC-14. The answer call's first message is SystemMessage(FLOW_ANSWER_PROMPT)."""
    assert isinstance(FLOW_ANSWER_PROMPT, str) and FLOW_ANSWER_PROMPT.strip()
    r = run("q", [(SEARCH, {"query": "x"})], docs={"x": [doc("Doc.", "data/a.md")]})
    first = r.llm.stream_calls[0][0]
    assert isinstance(first, SystemMessage)
    assert first.content == FLOW_ANSWER_PROMPT
    assert isinstance(r.llm.stream_calls[0][-1], HumanMessage)


def test_flow_nodes_constant():
    """Covers: AC-4 (right), EC-14, NFR-1. FLOW_NODES is exactly ('plan', 'run', 'reply')."""
    assert FLOW_NODES == ("plan", "run", "reply")


def test_top_k_constant():
    """Covers: AC-4 (right), contract. TOP_K is 3."""
    assert TOP_K == 3


def test_graph_contains_the_three_nodes(make_llm, make_store):
    """Covers: AC-4 (right), EC-14, NFR-1. The compiled graph has nodes named plan, run and reply."""
    graph = build_flow_graph(make_llm(), make_store(), tool_runners={})
    nodes = set(graph.get_graph().nodes)
    assert set(FLOW_NODES) <= nodes
    assert nodes - set(FLOW_NODES) <= {"__start__", "__end__"}


def test_graph_builds_with_a_separate_planner(make_llm, make_store):
    """Covers: AC-4 (boundary), EC-14. build_flow_graph accepts planner_llm and tool_runners."""
    graph = build_flow_graph(make_llm(), make_store(), planner_llm=make_llm(), tool_runners={})
    assert set(FLOW_NODES) <= set(graph.get_graph().nodes)


def test_building_the_graph_calls_no_model_store_or_runner(make_llm, make_store, make_runner):
    """Covers: AC-4 (boundary), NFR-5. Building the graph does nothing with the model or store."""
    llm, planner, store = make_llm(), make_llm(), make_store()
    runners = {BEV: make_runner(), REC: make_runner()}
    build_flow_graph(llm, store, planner_llm=planner, tool_runners=runners)
    assert llm.bind_calls == [] and llm.stream_calls == [] and llm.invoke_calls == []
    assert planner.bind_calls == [] and planner.invoke_calls == []
    assert store.calls == []
    assert runners[BEV].calls == [] and runners[REC].calls == []


# ---------------------------------------------------------------- EC-15 default runners

def test_default_tool_runners_have_exactly_the_two_tool_names():
    """Covers: AC-4 (right), EC-15; spec 030 AC-4. Keys are exactly calculate_bev_item, scale_recipe and
    calculate_food_item, each callable."""
    assert set(DEFAULT_TOOL_RUNNERS) == {BEV, REC, "calculate_food_item", "calculate_serving_utensils",
                                         "calculate_always_items"}
    assert all(callable(v) for v in DEFAULT_TOOL_RUNNERS.values())


def test_importing_blc_flow_reads_no_file_under_data():
    """Covers: AC-4 (right), EC-15, NFR-2. A fresh interpreter that imports blc.flow opens no file
    under the project's data/ directory (checked with an audit hook)."""
    src = Path(flow_pkg.__file__).resolve().parents[2]
    root = src.parent
    code = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        data = (Path(sys.argv[1]) / "data").resolve()
        opened = []
        def hook(event, args):
            if event == "open" and args and isinstance(args[0], (str, bytes)):
                p = args[0].decode() if isinstance(args[0], bytes) else args[0]
                try:
                    Path(p).resolve().relative_to(data)
                except ValueError:
                    return
                opened.append(p)
        sys.addaudithook(hook)
        import blc.flow
        print("OPENED:" + repr(opened))
        """
    )
    env = {"PYTHONPATH": str(src) + ":" + str(root / "scripts")}
    import os
    env = {**os.environ, **env}
    out = subprocess.run([sys.executable, "-c", code, str(root.parent)], capture_output=True, text=True,
                         env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "OPENED:[]" in out.stdout, out.stdout


# ---------------------------------------------------------------- NFR-6 prompt has no eval question

def test_prompt_contains_no_eval_question_word_for_word(eval_cases):
    """Covers: NFR-6 (wrong). None of the 30 eval questions (T1 to M10) appears in FLOW_ANSWER_PROMPT."""
    assert len(eval_cases) == 30
    leaked = [c["id"] for c in eval_cases if c["question"] in FLOW_ANSWER_PROMPT]
    assert leaked == []


@pytest.mark.parametrize("word", ["simple", "straightforward", "grounded"])
def test_prompt_has_the_grounding_words(word):
    """Covers: spec 020 AC-4 (right), spec 019 revision 1, section 4.4. FLOW_ANSWER_PROMPT contains
    'simple', 'straightforward' and 'grounded' (ignoring case)."""
    assert word in FLOW_ANSWER_PROMPT.lower()


def test_eval_cases_ids_are_t_d_m(eval_cases):
    """Covers: AC-5 (boundary), EC-16. The case list has T1..T10, D1..D10, M1..M10 (guards the copy)."""
    ids = [c["id"] for c in eval_cases]
    assert ids == [f"{p}{n}" for p in "TDM" for n in range(1, 11)]

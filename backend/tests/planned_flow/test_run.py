"""Spec 019, AC-1 (run): what the run node does with the planned calls.

EC-1 to EC-4, EC-8 and EC-10. Unit: scripted fake models, fake store, fake runners.
"""
import pytest
from langchain_core.messages import HumanMessage

from blc.flow import TOP_K, ToolResult

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
BEV_ARGS = {"item": "cambros", "drinks": ["iced tea"], "gallons": [6]}


def _contents(docs):
    return [d.page_content for d in docs]


# ---------------------------------------------------------------- EC-1 DOCS

def test_docs_turn_searches_once_with_top_k(run, doc):
    """Covers: AC-1 (right), EC-1. One search call -> similarity_search once with (query, k=3)."""
    d1 = doc("The coffee is under the machine.", "data/supplies/coffee.md")
    d2 = doc("Creamer is in the fridge.", "data/supplies/creamer.md")
    r = run("Where is the coffee?", [(SEARCH, {"query": "where is the coffee"})],
            docs={"where is the coffee": [d1, d2]})
    assert TOP_K == 3
    assert r.store.calls == [("where is the coffee", 3)]


def test_docs_turn_answer_message_has_chunks_sources_and_question(run, doc, text_of):
    """Covers: AC-1 (right), EC-1. The answer model is called once, through stream; its last message
    holds both chunks' text and source paths and the question."""
    d1 = doc("The coffee is under the machine.", "data/supplies/coffee.md")
    d2 = doc("Creamer is in the fridge.", "data/supplies/creamer.md")
    r = run("Where is the coffee?", [(SEARCH, {"query": "where is the coffee"})],
            docs={"where is the coffee": [d1, d2]})
    assert len(r.llm.stream_calls) == 1
    last = r.llm.stream_calls[0][-1]
    assert isinstance(last, HumanMessage)
    for token in ("The coffee is under the machine.", "data/supplies/coffee.md",
                  "Creamer is in the fridge.", "data/supplies/creamer.md", "Where is the coffee?"):
        assert token in last.content


def test_docs_turn_outcome_fields(run, doc):
    """Covers: AC-1 (right), EC-1. 1 search, 0 tools, 2 documents, answered_by_model True."""
    d1 = doc("The coffee is under the machine.", "data/supplies/coffee.md")
    d2 = doc("Creamer is in the fridge.", "data/supplies/creamer.md")
    r = run("Where is the coffee?", [(SEARCH, {"query": "where is the coffee"})],
            docs={"where is the coffee": [d1, d2]})
    o = r.outcome
    assert len(o.searches) == 1 and o.tools == ()
    assert o.searches[0].query == "where is the coffee"
    assert _contents(o.searches[0].chunks) == _contents([d1, d2])
    assert _contents(o.documents) == _contents([d1, d2])
    assert o.answered_by_model is True
    assert o.plan.route == "DOCS"


def test_question_is_stripped_in_outcome_and_message(run, doc):
    """Covers: AC-1 (boundary), EC-1. Outer whitespace is removed from the question."""
    d1 = doc("The coffee is under the machine.", "data/supplies/coffee.md")
    r = run("  Where is the coffee?\n", [(SEARCH, {"query": "where is the coffee"})],
            docs={"where is the coffee": [d1]})
    assert r.outcome.question == "Where is the coffee?"
    assert "Where is the coffee?" in r.llm.stream_calls[0][-1].content


def test_search_with_no_chunks_for_a_query_is_recorded_empty(run, doc):
    """Covers: AC-1 (boundary). A search the store answers with nothing still has a SearchResult."""
    d1 = doc("Cambros live by the sink.", "data/equipment/cambros.md")
    r = run("Where are cambros and tongs?",
            [(SEARCH, {"query": "cambros"}), (SEARCH, {"query": "tongs"})],
            docs={"cambros": [d1]})
    assert [s.query for s in r.outcome.searches] == ["cambros", "tongs"]
    assert r.outcome.searches[1].chunks == ()
    assert _contents(r.outcome.documents) == ["Cambros live by the sink."]


# ---------------------------------------------------------------- EC-2 TOOL

def test_tool_turn_runs_runner_once_with_exact_args_and_no_store(run, doc, make_runner):
    """Covers: AC-1 (right), EC-2. The bev runner is called once with exactly the planned args;
    the store is never called."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    trap = {"anything": [doc("trap", "data/trap.md")]}
    r = run("How many cambros for 6 gallons of iced tea?", [(BEV, BEV_ARGS)],
            runners=runners, docs=trap)
    assert runners[BEV].calls == [BEV_ARGS]
    assert runners[REC].calls == []
    assert r.store.calls == []


def test_tool_turn_message_has_tool_text_and_no_source(run, make_runner):
    """Covers: AC-1 (right), EC-2. The answer message holds the runner's text and no source path."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("How many cambros for 6 gallons of iced tea?", [(BEV, BEV_ARGS)], runners=runners)
    assert len(r.llm.stream_calls) == 1
    last = r.llm.stream_calls[0][-1]
    assert isinstance(last, HumanMessage)
    assert "Use 2 cambros." in last.content
    assert "data/" not in last.content
    assert ".md" not in last.content


def test_tool_turn_outcome_fields(run, make_runner):
    """Covers: AC-1 (right), EC-2. 0 searches, 1 tool result (as planned), 0 documents."""
    runners = {BEV: make_runner("ok", "Use 2 cambros."), REC: make_runner("ok", "x")}
    r = run("How many cambros for 6 gallons of iced tea?", [(BEV, BEV_ARGS)], runners=runners)
    o = r.outcome
    assert o.searches == () and o.documents == ()
    assert o.tools == (ToolResult(BEV, BEV_ARGS, "ok", "Use 2 cambros."),)
    assert o.plan.route == "TOOL"
    assert o.answered_by_model is True


def test_tool_status_and_text_are_recorded_and_shown_whatever_the_status(run, make_runner):
    """Covers: AC-1 (wrong), EC-2. A tool that returns status invalid is recorded as is and its
    text still reaches the answer model (no argument check, no retry)."""
    bad_args = {"item": "cambros", "drinks": ["iced tea"], "gallons": []}
    runners = {BEV: make_runner("invalid", "gallons is empty"), REC: make_runner("ok", "x")}
    r = run("How many cambros for iced tea?", [(BEV, bad_args)], runners=runners)
    assert runners[BEV].calls == [bad_args]
    assert r.outcome.tools[0].status == "invalid"
    assert "gallons is empty" in r.llm.stream_calls[0][-1].content
    assert len(r.llm.stream_calls) == 1


# ---------------------------------------------------------------- EC-3 BOTH

def test_both_turn_runs_store_and_recipe_runner_and_shows_both(run, doc, make_runner):
    """Covers: AC-1 (right), EC-3. A search plus scale_recipe: store once, recipe runner once, and the
    answer message has the tool text and the chunk text with its source."""
    chunk = doc("Lemon concentrate is on the top shelf.", "data/supplies/lemon.md")
    runners = {BEV: make_runner("ok", "BEV"), REC: make_runner("ok", "Use 14 oz of concentrate.")}
    rec_args = {"recipe": "lemonade", "gallons": 3}
    r = run("Where is the lemon concentrate, and how much for 3 gallons of lemonade?",
            [(SEARCH, {"query": "where is the lemon concentrate"}), (REC, rec_args)],
            runners=runners, docs={"where is the lemon concentrate": [chunk]})
    assert r.store.calls == [("where is the lemon concentrate", 3)]
    assert runners[REC].calls == [rec_args]
    assert runners[BEV].calls == []
    last = r.llm.stream_calls[0][-1].content
    for token in ("Use 14 oz of concentrate.", "Lemon concentrate is on the top shelf.",
                  "data/supplies/lemon.md"):
        assert token in last
    assert r.outcome.plan.route == "BOTH"


def test_both_turn_keeps_plan_order_within_searches_and_tools(run, doc, make_runner):
    """Covers: AC-1 (right), EC-3. Interleaved plan: searches and tools each keep plan order."""
    runners = {BEV: make_runner("ok", "bev text"), REC: make_runner("ok", "rec text")}
    r = run("q", [(SEARCH, {"query": "first"}), (BEV, BEV_ARGS),
                  (SEARCH, {"query": "second"}), (REC, {"recipe": "lemonade"})],
            runners=runners,
            docs={"first": [doc("one", "data/a.md")], "second": [doc("two", "data/b.md")]})
    assert [s.query for s in r.outcome.searches] == ["first", "second"]
    assert [t.name for t in r.outcome.tools] == [BEV, REC]
    assert [q for q, _ in r.store.calls] == ["first", "second"]
    assert _contents(r.outcome.documents) == ["one", "two"]


def test_two_tool_calls_both_run(run, make_runner):
    """Covers: AC-1 (right). Two TOOL parts: each runner is called once with its own args."""
    runners = {BEV: make_runner("ok", "bev text"), REC: make_runner("ok", "rec text")}
    rec_args = {"recipe": "lemonade", "gallons": 4}
    bev_args = {"item": "cambros", "drinks": ["lemonade"], "gallons": [4]}
    r = run("How do I make 4 gallons of lemonade?", [(REC, rec_args), (BEV, bev_args)], runners=runners)
    assert runners[REC].calls == [rec_args] and runners[BEV].calls == [bev_args]
    assert [t.name for t in r.outcome.tools] == [REC, BEV]
    assert r.outcome.tools[0].args == rec_args


def test_duplicate_search_calls_each_hit_the_store(run, doc):
    """Covers: AC-1 (boundary), EC-3. The store is searched once per search call, even for the same query."""
    d = doc("text", "data/a.md")
    r = run("q", [(SEARCH, {"query": "same"}), (SEARCH, {"query": "same"})], docs={"same": [d]})
    assert r.store.calls == [("same", 3), ("same", 3)]
    assert len(r.outcome.searches) == 2
    assert _contents(r.outcome.documents) == ["text"]


# ---------------------------------------------------------------- EC-4 duplicates

def test_shared_chunk_kept_in_each_search_and_once_in_documents(run, doc):
    """Covers: AC-1 (right), EC-4. A chunk with the same text and source from two searches stays in
    both SearchResults, and appears once in documents at its first position."""
    shared = doc("Shared text.", "data/shared.md")
    shared_again = doc("Shared text.", "data/shared.md")
    a = doc("Only in A.", "data/a.md")
    b = doc("Only in B.", "data/b.md")
    r = run("q", [(SEARCH, {"query": "qa"}), (SEARCH, {"query": "qb"})],
            docs={"qa": [a, shared], "qb": [shared_again, b]})
    s1, s2 = r.outcome.searches
    assert _contents(s1.chunks) == ["Only in A.", "Shared text."]
    assert _contents(s2.chunks) == ["Shared text.", "Only in B."]
    assert _contents(r.outcome.documents) == ["Only in A.", "Shared text.", "Only in B."]


def test_same_text_different_source_is_not_a_duplicate(run, doc):
    """Covers: AC-1 (boundary), EC-4. Same page_content but another source: both kept."""
    r = run("q", [(SEARCH, {"query": "qa"}), (SEARCH, {"query": "qb"})],
            docs={"qa": [doc("Same.", "data/a.md")], "qb": [doc("Same.", "data/b.md")]})
    assert [d.metadata["source"] for d in r.outcome.documents] == ["data/a.md", "data/b.md"]


def test_same_source_different_text_is_not_a_duplicate(run, doc):
    """Covers: AC-1 (boundary), EC-4. Same source, different page_content: both kept."""
    r = run("q", [(SEARCH, {"query": "qa"})],
            docs={"qa": [doc("Part one.", "data/a.md"), doc("Part two.", "data/a.md")]})
    assert _contents(r.outcome.documents) == ["Part one.", "Part two."]


def test_duplicate_within_one_search_is_listed_once_in_documents_only(run, doc):
    """Covers: AC-1 (boundary), EC-4. A repeat inside one search stays in its SearchResult."""
    r = run("q", [(SEARCH, {"query": "qa"})],
            docs={"qa": [doc("Dup.", "data/a.md"), doc("Dup.", "data/a.md")]})
    assert len(r.outcome.searches[0].chunks) == 2
    assert _contents(r.outcome.documents) == ["Dup."]


# ---------------------------------------------------------------- EC-8 tool errors

def test_runner_that_raises_gives_error_result_and_the_turn_finishes(run, make_runner):
    """Covers: AC-1 (wrong), EC-8. A raising runner -> ToolResult(name, args, 'error', 'error: bad');
    the turn still ends with an answer call."""
    runners = {BEV: make_runner(raises=ValueError("bad")), REC: make_runner("ok", "x")}
    r = run("How many cambros for 6 gallons of iced tea?", [(BEV, BEV_ARGS)], runners=runners)
    assert r.outcome.tools == (ToolResult(BEV, BEV_ARGS, "error", "error: bad"),)
    assert len(r.llm.stream_calls) == 1
    assert "error: bad" in r.llm.stream_calls[0][-1].content
    assert r.outcome.answered_by_model is True


def test_missing_runner_gives_no_runner_error_and_the_turn_finishes(run, make_runner):
    """Covers: AC-1 (wrong), EC-8. A tool name with no runner -> 'error: no runner for <name>'."""
    runners = {BEV: make_runner("ok", "x")}  # no scale_recipe
    rec_args = {"recipe": "lemonade"}
    r = run("q", [(REC, rec_args)], runners=runners)
    assert r.outcome.tools == (ToolResult(REC, rec_args, "error", f"error: no runner for {REC}"),)
    assert len(r.llm.stream_calls) == 1
    assert r.outcome.answered_by_model is True


def test_a_raising_runner_does_not_stop_the_next_tool(run, make_runner):
    """Covers: AC-1 (boundary), EC-8. The tool after a failing one still runs."""
    runners = {BEV: make_runner(raises=RuntimeError("boom")), REC: make_runner("ok", "rec text")}
    r = run("q", [(BEV, BEV_ARGS), (REC, {"recipe": "lemonade"})], runners=runners)
    assert [t.status for t in r.outcome.tools] == ["error", "ok"]
    assert r.outcome.tools[0].text == "error: boom"
    assert len(runners[REC].calls) == 1


def test_a_failing_tool_does_not_hide_the_documents(run, make_runner, doc):
    """Covers: AC-1 (right), EC-8. Error result plus search: both reach the answer message."""
    runners = {BEV: make_runner(raises=ValueError("bad")), REC: make_runner("ok", "x")}
    r = run("q", [(SEARCH, {"query": "qa"}), (BEV, BEV_ARGS)], runners=runners,
            docs={"qa": [doc("Doc text.", "data/a.md")]})
    last = r.llm.stream_calls[0][-1].content
    assert "error: bad" in last and "Doc text." in last and "data/a.md" in last


# ---------------------------------------------------------------- EC-10 fallback

def test_planner_fallback_searches_the_stripped_question(run, mk, doc):
    """Covers: AC-1 (right), EC-10. No planned call -> the store is searched with the stripped
    question, and the turn continues as DOCS."""
    d = doc("The coffee is under the machine.", "data/supplies/coffee.md")
    r = run("  Where is the coffee?  ", plan_reply=mk.ai(content="The coffee is under the machine."),
            docs={"Where is the coffee?": [d]})
    assert r.store.calls == [("Where is the coffee?", 3)]
    assert r.outcome.plan.route == "DOCS"
    assert r.outcome.plan.fallback is True
    assert _contents(r.outcome.documents) == ["The coffee is under the machine."]
    assert r.outcome.answered_by_model is True


def test_planner_with_only_unknown_tools_also_falls_back_to_search(run, mk):
    """Covers: AC-1 (wrong), EC-10. Only unknown tool names -> same fallback search."""
    r = run("Where is the tea?", plan_reply=mk.ai(("make_coffee", {"x": 1})))
    assert r.store.calls == [("Where is the tea?", 3)]


# ---------------------------------------------------------------- errors propagate

def test_store_error_propagates(run):
    """Covers: AC-1 (wrong). Errors from the store are not swallowed."""
    with pytest.raises(RuntimeError, match="store down"):
        run("q", [(SEARCH, {"query": "x"})], store_raises=RuntimeError("store down"))


def test_planner_error_propagates(run, make_llm, make_store):
    """Covers: AC-1 (wrong). Errors from the planner model are not swallowed."""
    from blc.flow import run_planned_turn

    llm = make_llm(plan_raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        run_planned_turn(llm, make_store(), "q", None, tool_runners={})


def test_answer_model_error_propagates(run, make_llm, make_store, mk):
    """Covers: AC-1 (wrong). Errors from the answer model's stream are not swallowed."""
    from blc.flow import run_planned_turn

    llm = make_llm(plan_reply=mk.ai((SEARCH, {"query": "x"})), stream_raises=RuntimeError("gpu"))
    store = make_store({"x": []})
    with pytest.raises(RuntimeError):
        # an empty search would skip the answer call, so give it a chunk
        from langchain_core.documents import Document
        store.results["x"] = [Document(page_content="t", metadata={"source": "data/a.md"})]
        run_planned_turn(llm, store, "q", None, tool_runners={})

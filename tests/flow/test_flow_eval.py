"""AC-5: the end-to-end flow eval (spec 011 sections 4.5 and 4.6). Real model, real store, baseline only.

Every case E1 to E21 is run once (run_turn with generate=False, cached per case in the session
fixture flow_env); its stage checks are separate tests so a run shows which stage failed. All tests
are marked `eval` and skip, not fail, when Ollama, the chat model or the Chroma store is missing.
Pass threshold: none. Failing stages are findings, reported by case and stage with the trace.
Expected values come from the table in section 4.6 and the calculator's own result (NFR-6).
"""

from __future__ import annotations

import pytest

import chat
from blc.trace import format_trace

pytestmark = pytest.mark.eval


def _fail(case, stage, problems, trace):
    return f"{case['id']} {stage} failed: " + "; ".join(problems) + "\n" + format_trace(trace)


def test_stage1_prompt(case, get_trace):
    """Covers: AC-5 stage 1 (right). trace.question is the case's question (stripped) and trace.history equals the case's history."""
    trace = get_trace(case)
    problems = []
    if trace.question != case["question"].strip():
        problems.append(f"question {trace.question!r} != {case['question'].strip()!r}")
    if tuple(trace.history) != tuple(case["history"]):
        problems.append(f"history {trace.history!r} != {tuple(case['history'])!r}")
    assert not problems, _fail(case, "stage 1 (prompt)", problems, trace)


def test_stage2_route(case, get_trace):
    """Covers: AC-5 stage 2 (right). trace.route is set and its kind is the expected kind; the message shows the parts and the fallback and unfaithful flags."""
    trace = get_trace(case)
    assert trace.route is not None, _fail(case, "stage 2 (route)", ["route is None"], trace)
    shown = (f"kind {trace.route.kind!r} != {case['kind']!r}; parts "
             f"{[(p.route, p.text) for p in trace.route.parts]}; fallback={trace.route.fallback}; "
             f"unfaithful={getattr(trace.route, 'unfaithful', False)}")
    assert trace.route.kind == case["kind"], _fail(case, "stage 2 (route)", [shown], trace)


def test_stage3_retrieval(docs_case, get_trace, stage_checks):
    """Covers: AC-5 stage 3 (right). The expected sources are among the retrieved chunks and every must-include word occurs in their texts (cases of kind DOCS or BOTH that list sources)."""
    trace = get_trace(docs_case)
    problems = stage_checks.stage3(docs_case, trace)
    assert not problems, _fail(docs_case, "stage 3 (retrieval)", problems, trace)


def test_stage4_tool(tool_case, get_trace, stage_checks):
    """Covers: AC-5 stage 4 (right). Exactly one ToolStage with a usable tool_text, and every call that was not refused has the right name, item, status, drinks and guests (cases of kind TOOL or BOTH)."""
    trace = get_trace(tool_case)
    problems = stage_checks.stage4(tool_case, trace)
    assert not problems, _fail(tool_case, "stage 4 (tool)", problems, trace)


def test_stage5_both(both_case, get_trace, stage_checks):
    """Covers: AC-5 stage 5 (right). For a BOTH case, stage 3 and stage 4 both hold."""
    trace = get_trace(both_case)
    problems = [f"stage 3: {p}" for p in stage_checks.stage3(both_case, trace)]
    problems += [f"stage 4: {p}" for p in stage_checks.stage4(both_case, trace)]
    assert not problems, _fail(both_case, "stage 5 (both)", problems, trace)


def test_eval_cases_match_the_spec_table(case):
    """Covers: AC-5 (right). Sanity check of the case table itself: DOCS and BOTH cases list the kind's data, TOOL and BOTH cases list a tool expectation, and the kinds are valid (no model needed)."""
    assert case["kind"] in ("DOCS", "TOOL", "BOTH")
    if case["kind"] in ("TOOL", "BOTH"):
        assert case["tool"] is not None
        assert case["tool"]["recipe"] if case["tool"].get("name") == "scale_recipe" else case["tool"]["item"]
    else:
        assert case["tool"] is None
    if case["kind"] == "BOTH":
        assert case["sources"]
    assert chat.TOP_K >= 1

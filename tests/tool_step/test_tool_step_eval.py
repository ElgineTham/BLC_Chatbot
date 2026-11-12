"""Spec 008: tool-step eval, cases S1 to S28 (one test per case via parametrize ids).

Marked eval. Skips (does not fail) when Ollama is not running or the chat model is missing (EC-1).
Spec 009 AC-5: pass threshold is all 28 cases S1 to S28. Only run_tool_step and
run_bev_tool are called; the router, retrieval and run_turn are never used (AC-4).
Reads the real menu and rules under data/pull_sheet/; writes nothing (EC-2).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


def test_tool_step_case(case, bound_model, check_call, describe_drinks):
    """Covers: AC-1, AC-2, AC-3, AC-5 (right/wrong per case S1-S28), EC-1, EC-3 to EC-9, AC-6, NFR-2.

    Applies checks 1 to 5 of section 4.1 to every call the real model makes for the case's
    question, plus the revision 1 rules: no invented guests/gallons for number-free questions
    (S3, S6, S16, S19, S25; EC-8) and names-only drinks looked up in BevResult.text (S16, S19,
    S25; EC-9). A wrong call that is later corrected still fails the case (EC-7, section 4.1).
    """
    from blc.router import RoutedPart
    from blc.tool_step import REJECTED_PREFIX
    from blc.tools.bev_tools import BEV_TOOL
    from chat import TOOL_LIMIT_REPLY, run_tool_step

    outcome = run_tool_step(bound_model, (BEV_TOOL,), RoutedPart("TOOL", case["question"]))

    # Spec 009 AC-5: a record whose result starts with REJECTED_PREFIX was refused by the argument
    # check and never ran, so checks 2 to 4 skip it; checks 1 and 5 apply as before. Refused calls
    # are listed with their reasons in the failure message.
    failed = []
    details = []
    refused = [r for r in outcome.records if str(r.result).startswith(REJECTED_PREFIX)]
    ran = [r for r in outcome.records if r not in refused]
    if not outcome.records or outcome.tool_text is None:
        failed.append("check 1 (called): the model made no call")
    for rec in ran:
        errors, status, drinks = check_call(case, rec)
        details.append(f"  call name={rec.name!r} args={rec.args!r} -> status={status!r} "
                       f"drinks={describe_drinks(drinks)}")
        failed += errors
    if outcome.tool_text == TOOL_LIMIT_REPLY:
        failed.append("check 5 (not stuck): the step ended with the tool-limit reply")

    refused_lines = [f"  refused call name={r.name!r} args={r.args!r} reason={r.result!r}" for r in refused]
    message = (
        f"{case['id']}: {case['question']!r}\n"
        + ("\n".join(details) if details else "  (no calls ran)")
        + ("\n" + "\n".join(refused_lines) if refused_lines else "")
        + f"\n  retried={outcome.retried}\n  failed checks:\n    "
        + "\n    ".join(failed)
    )
    assert not failed, message

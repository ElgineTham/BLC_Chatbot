"""Check a plan for invented numbers, ask the planner once more, drop what is still invented (spec 021 section 4.3)."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from blc.flow.invented import RejectedCall, invented_numbers
from blc.planner import NO_INVENTED_RULE, Plan, PlannedCall, plan_question

FEEDBACK_HEADER = "Your previous plan used numbers the user never gave. " + NO_INVENTED_RULE
FEEDBACK_LINE = "- {name}: {arguments}"


@dataclass(frozen=True)
class CheckedPlan:
    first_plan: Plan
    plan: Plan
    rejected: tuple[RejectedCall, ...]
    retried: bool


def find_rejected(
    plan: Plan, question: str, history: list[dict[str, str]]
) -> tuple[RejectedCall, ...]:
    rejected: list[RejectedCall] = []
    for call in plan.calls:
        invented = invented_numbers(call.name, call.args, question, history)
        if invented:
            rejected.append(RejectedCall(call.name, dict(call.args), invented))
    return tuple(rejected)


def build_feedback(rejected: tuple[RejectedCall, ...]) -> str:
    lines = [FEEDBACK_HEADER]
    for call in rejected:
        arguments = "; ".join(
            f"{key} = {', '.join(str(value) for value in values)}" for key, values in call.invented.items()
        )
        lines.append(FEEDBACK_LINE.format(name=call.name, arguments=arguments))
    return "\n".join(lines)


def drop_invented(plan: Plan, question: str, history: list[dict[str, str]]) -> Plan:
    """The plan with every still-invented argument removed from its call."""
    calls: list[PlannedCall] = []
    for call in plan.calls:
        invented = invented_numbers(call.name, call.args, question, history)
        args = {key: value for key, value in call.args.items() if key not in invented}
        calls.append(PlannedCall(call.name, args) if invented else call)
    return Plan(plan.route, tuple(calls), plan.fallback)


def check_plan(
    planner: BaseChatModel, question: str, history: list[dict[str, str]], first: Plan
) -> CheckedPlan:
    """At most one more planner call; the second plan replaces the first."""
    rejected = find_rejected(first, question, history)
    if not rejected:
        return CheckedPlan(first, first, (), False)
    second = plan_question(planner, question, history, feedback=build_feedback(rejected))
    return CheckedPlan(first, drop_invented(second, question, history), rejected, True)

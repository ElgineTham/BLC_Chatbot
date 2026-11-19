"""Runs one planned tool call on the real tool (spec 019 section 4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from blc.tools.bev_tools import run_bev_tool
from blc.tools.food_tools import run_food_tool
from blc.tools.recipe_tools import run_recipe_tool
from blc.tools.serv_tools import SERV_TOOL_NAME, run_serv_tool

ERROR_STATUS = "error"
NO_RUNNER_TEXT = "error: no runner for {name}"
ERROR_TEXT = "error: {message}"


@dataclass(frozen=True)
class ToolOutput:
    status: str
    text: str


ToolRunner = Callable[[dict[str, object]], ToolOutput]


def _run_bev(args: dict[str, object]) -> ToolOutput:
    result = run_bev_tool(args)
    return ToolOutput(result.status, result.text)


def _run_recipe(args: dict[str, object]) -> ToolOutput:
    result = run_recipe_tool(args)
    return ToolOutput(result.status, result.text)


def _run_food(args: dict[str, object]) -> ToolOutput:
    result = run_food_tool(args)
    return ToolOutput(result.status, result.text)


def _run_serv(args: dict[str, object]) -> ToolOutput:
    result = run_serv_tool(args)
    return ToolOutput(result.status, result.text)


DEFAULT_TOOL_RUNNERS: Mapping[str, ToolRunner] = {
    "calculate_bev_item": _run_bev,
    "scale_recipe": _run_recipe,
    "calculate_food_item": _run_food,
    SERV_TOOL_NAME: _run_serv,
}


def run_tool(runners: Mapping[str, ToolRunner], name: str, args: dict[str, object]) -> ToolOutput:
    """Run one tool; a missing runner or a raised error becomes an "error" output."""
    runner = runners.get(name)
    if runner is None:
        return ToolOutput(ERROR_STATUS, NO_RUNNER_TEXT.format(name=name))
    try:
        return runner(args)
    except Exception as error:  # noqa: BLE001 - a tool failure must not stop the turn
        return ToolOutput(ERROR_STATUS, ERROR_TEXT.format(message=error))

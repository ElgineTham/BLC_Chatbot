"""Shared helpers for the spec 044 (always tool) tests."""
import pytest

from blc.tools.always_tools import AlwaysResult, run_always_tool


@pytest.fixture
def run():
    """run_always_tool wrapper that also checks the return type."""

    def _run(args):
        result = run_always_tool(args)
        assert isinstance(result, AlwaysResult)
        return result

    return _run


@pytest.fixture
def expected_calc_1():
    """The CALC-1 counts (tables 2, drip_trays 3)."""
    return {"black linens": 5, "black napkins": 3, "purple napkins": 4}

"""Spec 044 section 6.2 ARGS: raw argument handling in run_always_tool."""
import pytest


@pytest.mark.parametrize("tables", [2, 2.0, "2", " 2 "])
def test_args_1_accepted_forms(run, tables, expected_calc_1):
    """Covers: AC-5 (right), ARGS-1. 2, 2.0, "2", " 2 " all mean 2."""
    r = run({"tables": tables, "drip_trays": 3})
    assert r.status == "ok"
    assert r.counts == expected_calc_1


@pytest.mark.parametrize("trays", [3, 3.0, "3", " 3 "])
def test_args_1_drip_trays_accepted_forms(run, trays, expected_calc_1):
    """Covers: AC-5 (right). Extra: drip_trays accepts the same forms."""
    r = run({"tables": 2, "drip_trays": trays})
    assert r.status == "ok"
    assert r.counts == expected_calc_1


def test_args_2_extra_key_ignored(run, expected_calc_1):
    """Covers: AC-5 (right), ARGS-2. Unknown keys are ignored."""
    r = run({"tables": 2, "drip_trays": 3, "guests": 70})
    assert r.status == "ok"
    assert r.counts == expected_calc_1


def test_zero_values_are_given(run):
    """Covers: AC-2 (boundary), AC-3. 0, "0" and 0.0 are values, not 'not given'."""
    for zero in (0, "0", 0.0):
        r = run({"tables": zero, "drip_trays": zero})
        assert r.status == "ok"
        assert r.counts == {"black linens": 0, "black napkins": 0, "purple napkins": 0}


@pytest.mark.parametrize("missing", ["MISSING", None, "", "  "])
def test_args_3_tables_not_given(run, missing):
    """Covers: AC-3 (wrong), ARGS-3. Missing/null/blank tables is need_info."""
    args = {"drip_trays": 3}
    if missing != "MISSING":
        args["tables"] = missing
    r = run(args)
    assert r.status == "need_info"
    assert r.checks == ("bus tubs", "towels")
    assert r.counts == {"black napkins": 3}


@pytest.mark.parametrize("missing", ["MISSING", None, "", "  "])
def test_args_3_drip_trays_not_given(run, missing):
    """Covers: AC-3 (wrong). Extra: missing/null/blank drip_trays is need_info."""
    args = {"tables": 2}
    if missing != "MISSING":
        args["drip_trays"] = missing
    r = run(args)
    assert r.status == "need_info"
    assert r.counts == {"black linens": 5, "purple napkins": 4}


def test_args_4_both_missing(run):
    """Covers: AC-3 (wrong), ARGS-4. {} is need_info."""
    r = run({})
    assert r.status == "need_info"
    assert r.checks == ("bus tubs", "towels")
    assert r.counts == {}


@pytest.mark.parametrize(
    "bad", [-1, 2.5, "2.5", "two", True, [2], {"n": 2}, "-1"]
)
def test_args_5_invalid_tables(run, bad):
    """Covers: AC-4 (wrong), ARGS-5. Bad tables values are invalid, no exception."""
    r = run({"tables": bad, "drip_trays": 3})
    assert r.status == "invalid"
    assert r.checks is None
    assert r.counts is None


@pytest.mark.parametrize("bad", [-1, "three", False, True, 1.5, [1], {"n": 1}])
def test_args_6_invalid_drip_trays(run, bad):
    """Covers: AC-4 (wrong), ARGS-6. Bad drip_trays values are invalid."""
    r = run({"tables": 2, "drip_trays": bad})
    assert r.status == "invalid"
    assert r.checks is None
    assert r.counts is None


@pytest.mark.parametrize(
    "args",
    [
        {"tables": "two"},
        {"drip_trays": "three"},
        {"tables": -1, "drip_trays": None},
        {"tables": None, "drip_trays": -1},
        {"tables": "", "drip_trays": True},
    ],
)
def test_args_7_invalid_beats_need_info(run, args):
    """Covers: AC-4 (boundary), ARGS-7. One invalid value with the other missing is invalid."""
    assert run(args).status == "invalid"


@pytest.mark.parametrize("args", [[], [2, 3], "tables=2", None, 5, ["tables"]])
def test_args_8_non_mapping(run, args):
    """Covers: AC-4 (wrong), ARGS-8. Non-mapping args are invalid, no exception."""
    r = run(args)
    assert r.status == "invalid"
    assert r.checks is None
    assert r.counts is None

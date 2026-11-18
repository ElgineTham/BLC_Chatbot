"""Shared setup for spec 022 (keep the named drink). Written from the spec only.

Unit tests: no Ollama, no Chroma, no network, nothing read under data/ (NFR-4).
The test catalog is spec 005 Appendix A, written to tmp_path. Everything is exposed as fixtures so no test
imports from this module:
- catalog       the Appendix A catalog (load_catalog on a temp dir)
- names         N = menu_names(catalog)
- P             plan helpers: P.plan(route, *calls), P.bev(args), P.search(query), P.rec(args), P.only_bev(plan)
- run_fill      run one planned turn with scripted planner plans and fakes; returns a namespace
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

BEV = "calculate_bev_item"
REC = "scale_recipe"
SEARCH = "search_documents"
PKG = "Coffee, decaf, tea, iced water & juice"


def _menu():
    return {
        "items": {
            "Coffee": {"unit": "gallon", "also_written_as": ["Fresh-brewed coffee"], "tags": ["HOT", "COFFEE"]},
            "Decaf": {"unit": "gallon", "also_written_as": ["Fresh-brewed decaffeinated coffee"], "tags": ["HOT", "COFFEE"]},
            "Hot water": {
                "unit": "gallon",
                "also_written_as": ["Hot water with an assortment of black, green, and herbal tea bags"],
                "tags": ["HOT", "HOT-WATER"],
            },
            "Brewed hot cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
            "Ginger Honeycrisp apple cider": {"unit": "gallon", "also_written_as": [], "tags": ["HOT", "CIDER"]},
            "Iced water": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Iced tea": {"unit": "gallon", "also_written_as": ["Iced tea with lemon wedges"], "tags": ["COLD", "ICED-TEA"]},
            "Orange juice": {"unit": "gallon", "also_written_as": [], "tags": ["COLD", "JUICE"]},
            "Lemonade": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Peach tea": {"unit": "gallon", "also_written_as": [], "tags": ["COLD"]},
            "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []},
        },
        "packages": {
            PKG: {
                "includes": ["Coffee", "Decaf", "Hot water", "Iced water"],
                "placeholders": {"JUICE": "Orange juice"},
            }
        },
    }


def _rules():
    return {
        "cambros": [
            {"supply": "5 gal cambro", "gallons": 5},
            {"supply": "2 gal cambro", "gallons": 2},
            {"supply": "1 gal cambro", "gallons": 1},
        ],
        "supplies": [
            {"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"},
            {"supply": "cold-cups", "qty": 1, "per": "guest+extra", "when_tagged": "COLD"},
            {"supply": "Cocktail napkins", "tick": True},
            {"supply": "Creamer", "tick": True, "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"},
            {"supply": "Stir sticks", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemon tongs", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemons", "tick": True, "when_tagged": "HOT-WATER"},
            {"supply": "Tea packets", "qty": 1, "per": "event", "when_tagged": "HOT-WATER"},
            {"supply": "Lemons", "tick": True, "when_tagged": "ICED-TEA"},
        ],
        "extras": [
            {"guests_up_to": 20, "extra": 10},
            {"guests_up_to": 50, "extra": 20},
            {"guests_up_to": 100, "extra": 50},
            {"guests_up_to": None, "extra": 100},
        ],
    }


@pytest.fixture
def catalog(tmp_path):
    from blc.pull_sheet import load_catalog

    for rel, data in (("menu/beverages.json", _menu()), ("rules/beverages.json", _rules())):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return load_catalog(tmp_path)


@pytest.fixture
def names(catalog):
    from blc.pull_sheet import menu_names

    return menu_names(catalog)


@pytest.fixture(name="PKG")
def _pkg():
    return PKG


# --------------------------------------------------------------------------
# Plan helpers
# --------------------------------------------------------------------------

def _plan(route, *calls):
    from blc.planner import Plan

    return Plan(route, tuple(calls), False)


def _call(name, args):
    from blc.planner import PlannedCall

    return PlannedCall(name, args)


@pytest.fixture
def P():
    def only_bev(plan):
        """The single calculate_bev_item call of a plan."""
        found = [c for c in plan.calls if c.name == BEV]
        assert len(found) == 1
        return found[0]

    return SimpleNamespace(
        plan=_plan,
        bev=lambda args: _call(BEV, args),
        search=lambda q: _call(SEARCH, {"query": q}),
        rec=lambda args: _call(REC, args),
        only_bev=only_bev,
    )


# --------------------------------------------------------------------------
# Flow fakes (scripted planner and answer models, fake store, recording runners)
# --------------------------------------------------------------------------

class _Bound:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, messages, *args, **kwargs):
        self.parent.invoke_calls.append(messages)
        n = len(self.parent.plan_replies)
        i = len(self.parent.invoke_calls)
        if i > n:
            raise AssertionError(f"planner called {i} times; only {n} scripted")
        return self.parent.plan_replies[i - 1]


class FakeLLM:
    def __init__(self, plan_replies=(), pieces=("Answer.",)):
        self.plan_replies = list(plan_replies)
        self.pieces = list(pieces)
        self.invoke_calls = []
        self.stream_calls = []

    def bind_tools(self, tools, *args, **kwargs):
        return _Bound(self)

    def invoke(self, *args, **kwargs):
        raise AssertionError("invoke called on the unbound model")

    def stream(self, messages, *args, **kwargs):
        self.stream_calls.append(messages)
        return (AIMessageChunk(content=p) for p in self.pieces)


class FakeStore:
    def __init__(self):
        self.calls = []

    def similarity_search(self, query, k):
        self.calls.append((query, k))
        return []


class FakeRunner:
    def __init__(self, status="ok", text="TEXT"):
        self.status, self.text, self.calls = status, text, []

    def __call__(self, args):
        from blc.flow import ToolOutput

        self.calls.append(dict(args))
        return ToolOutput(self.status, self.text)


def _ai(calls):
    return AIMessage(content="", tool_calls=[
        {"name": n, "args": a, "id": f"call_{i}"} for i, (n, a) in enumerate(calls, 1)])


@pytest.fixture
def run_fill(catalog):
    """run_fill(question, plans, history=None, with_catalog=True, positional=False) -> namespace.

    plans: one entry per scripted planner reply; each entry is a list of (tool name, args).
    with_catalog False: drink_catalog is not passed at all."""

    def _run(question, plans, history=None, with_catalog=True, catalog_value="default", positional=False):
        from blc.flow import run_planned_turn

        llm = FakeLLM([_ai(p) for p in plans])
        store = FakeStore()
        runners = {BEV: FakeRunner(), REC: FakeRunner()}
        value = catalog if catalog_value == "default" else catalog_value
        if positional:
            # llm, store, question, history, on_token, planner_llm, tool_runners, drink_catalog
            outcome = run_planned_turn(llm, store, question, history, None, None, runners, value)
        else:
            kwargs = {"tool_runners": runners}
            if with_catalog:
                kwargs["drink_catalog"] = value
            outcome = run_planned_turn(llm, store, question, history, **kwargs)
        return SimpleNamespace(outcome=outcome, llm=llm, store=store, runners=runners)

    return _run

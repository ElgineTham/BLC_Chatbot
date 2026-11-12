"""Question router: labels each part of a question TOOL or DOCS (specs 006, 007)."""

from __future__ import annotations

from blc.router.decision import ROUTE_KINDS, ROUTES, RouteDecision, RoutedPart
from blc.router.drinks import MENU_DRINKS, menu_drinks_in
from blc.router.faithful import route_faithfully
from blc.router.fidelity import FIDELITY_PREFIX, check_fidelity
from blc.router.items import PULL_SHEET_ITEMS, pull_sheet_items_in
from blc.router.prompt import ROUTER_PROMPT, ROUTER_SCHEMA
from blc.router.route import route_question

__all__ = [
    "ROUTES", "ROUTE_KINDS", "RoutedPart", "RouteDecision", "ROUTER_PROMPT",
    "ROUTER_SCHEMA", "PULL_SHEET_ITEMS", "pull_sheet_items_in", "route_question",
    "MENU_DRINKS", "menu_drinks_in", "FIDELITY_PREFIX", "check_fidelity", "route_faithfully",
]

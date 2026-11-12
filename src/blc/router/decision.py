"""The router's result types and how a decision's kind follows from its parts."""

from __future__ import annotations

from dataclasses import dataclass

ROUTES: tuple[str, ...] = ("TOOL", "DOCS")
ROUTE_KINDS: tuple[str, ...] = ("TOOL", "DOCS", "BOTH")


@dataclass(frozen=True)
class RoutedPart:
    route: str  # "TOOL" or "DOCS"
    text: str   # the part as a self-contained question


@dataclass(frozen=True)
class RouteDecision:
    parts: tuple[RoutedPart, ...]  # at least one, in the order the model gave them
    kind: str                      # "TOOL", "DOCS" or "BOTH"
    fallback: bool                 # True if the model's reply could not be read
    unfaithful: bool = False       # True if the parts failed the fidelity check twice (spec 010)


def kind_of(parts: tuple[RoutedPart, ...]) -> str:
    routes = {part.route for part in parts}
    if routes == {"TOOL"}:
        return "TOOL"
    if routes == {"DOCS"}:
        return "DOCS"
    return "BOTH"

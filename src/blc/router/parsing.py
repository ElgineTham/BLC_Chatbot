"""Reads the router model's reply into a RouteDecision (spec 007 sections 4.1, 4.2)."""

from __future__ import annotations

import json
import re

from blc.router.decision import ROUTES, RouteDecision, RoutedPart, kind_of
from blc.router.items import pull_sheet_items_in

LABEL_LINE = re.compile(
    r"^[\s\-*#]*(?:\d+[.)]\s*)?\**\s*(TOOL|DOCS)\s*\**\s*:\s*\**\s*(.*)$",
    re.IGNORECASE,
)


def parse_line(line: str, question: str) -> RoutedPart | None:
    match = LABEL_LINE.match(line.strip())
    if match is None:
        return None
    text = match.group(2).strip()
    return RoutedPart(match.group(1).upper(), text or question)


def parse_json_parts(reply: str, question: str) -> tuple[RoutedPart, ...]:
    try:
        payload = json.loads(reply)
    except (TypeError, ValueError):
        return ()
    items = payload.get("parts") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return ()
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        route, text = item.get("route"), item.get("text")
        if not isinstance(route, str) or not isinstance(text, str):
            continue
        route = route.strip().upper()
        if route in ROUTES:
            parts.append(RoutedPart(route, text.strip() or question))
    return tuple(parts)


def parse_label_parts(reply: str, question: str) -> tuple[RoutedPart, ...]:
    return tuple(
        part
        for line in reply.splitlines()
        if line.strip() and (part := parse_line(line, question)) is not None
    )


def apply_guard(parts: tuple[RoutedPart, ...]) -> tuple[RoutedPart, ...]:
    """A TOOL part that mentions no pull sheet item becomes DOCS (spec 007 section 4.2)."""
    return tuple(
        RoutedPart("DOCS", part.text)
        if part.route == "TOOL" and not pull_sheet_items_in(part.text)
        else part
        for part in parts
    )


def parse_reply(reply: str, question: str) -> RouteDecision:
    parts = parse_json_parts(reply, question) or parse_label_parts(reply, question)
    if not parts:
        fallback_parts = (RoutedPart("DOCS", question),)
        return RouteDecision(fallback_parts, "DOCS", True)
    parts = apply_guard(parts)
    return RouteDecision(parts, kind_of(parts), False)

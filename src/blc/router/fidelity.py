"""Checks that the router kept the user's wording (spec 010 section 4.1). No I/O."""

from __future__ import annotations

import re

from blc.router.decision import RoutedPart
from blc.router.drinks import menu_drinks_in
from blc.router.items import PULL_SHEET_ITEMS, pull_sheet_items_in
from blc.tool_step.numbers import WORD_NUMBERS, numbers_in

FIDELITY_PREFIX: str = "invalid (rewrite): "
COPY_ADVICE = "Copy the user's own words exactly; do not paraphrase."
_EDGE_PUNCTUATION = " \t\r\n.,;:!?\"'()[]{}-_*#"
_NUMBER_TOKEN = re.compile(
    r"(?<![a-z0-9-])(?:"
    + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(WORD_NUMBERS, key=len, reverse=True))
    + r")(?![a-z0-9-])|(?<!\d)\d+(?:,\d{3})*(?:\.\d+)?",
    re.IGNORECASE,
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _normal_part(text: str) -> str:
    return _squash(text.strip(_EDGE_PUNCTUATION))


def _first_not_inside(question: str, texts: list[str]) -> str | None:
    squashed = _squash(question)
    for text in texts:
        if _normal_part(text) not in squashed:
            return text
    return None


def _lost_numbers(question: str, joined: str) -> list[str]:
    kept = numbers_in(joined)
    lost = []
    for match in _NUMBER_TOKEN.finditer(question):
        token = match.group(0)
        if numbers_in(token) - kept and token not in lost:
            lost.append(token)
    return lost


def _lost_items(question: str, joined: str) -> list[str]:
    kept = set(pull_sheet_items_in(joined))
    words: list[str] = []
    for item in pull_sheet_items_in(question):
        if item in kept:
            continue
        for word in PULL_SHEET_ITEMS[item]:
            if re.search(
                rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", question, re.IGNORECASE
            ):
                words.append(word)
    return words


def _preservation_loss(question: str, texts: list[str]) -> list[str]:
    joined = " ".join(texts)
    kept_drinks = set(menu_drinks_in(joined))
    lost = _lost_numbers(question, joined)
    lost += [d for d in menu_drinks_in(question) if d not in kept_drinks]
    lost += _lost_items(question, joined)
    return lost


def _reason(detail: str) -> str:
    return " ".join(f"{FIDELITY_PREFIX}{detail} {COPY_ADVICE}".split())


def check_fidelity(
    question: str,
    history: list[dict[str, str]],
    parts: tuple[RoutedPart, ...],
) -> str | None:
    """None if the parts are faithful to the question. Otherwise one line, starting with
    FIDELITY_PREFIX, that says what to change. Never raises. No I/O."""
    try:
        texts = [str(getattr(part, "text", "")) for part in parts]
        question = question if isinstance(question, str) else str(question)
        outside = _first_not_inside(question, texts)
        if outside is None:
            return None
        if not history:
            return _reason(f'"{outside}" is not copied from the question.')
        lost = _preservation_loss(question, texts)
        if not lost:
            return None
        names = ", ".join(f'"{word}"' for word in lost)
        return _reason(f"the rewrite lost {names} from the question.")
    except Exception:  # noqa: BLE001 - the check must never raise
        return _reason("the parts could not be checked.")

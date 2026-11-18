"""Item names found in the knowledge files, with the domains they belong to."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from blc.retrieval.domains import BEVERAGE, FOOD, NAPKIN

Lexicon = Mapping[str, frozenset[str]]

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data"
FOOD_FILE = Path("pull_sheet/menu/food.md")
NAPKIN_FILE = Path("pull_sheet/rules/napkins.md")
NAPKIN_NAMES = frozenset({"napkin", "napkins"})
BEVERAGE_MENU_FILE =Path("pull_sheet/menu/beverages.md")
BEVERAGE_DIRS = ("supplies", "recipes")
DRINKS_HEADING = "## Drinks served by the gallon"
MIN_TOKEN_LENGTH = 4
GENERIC_WORDS = frozenset(
    {
        "fresh", "assorted", "whole", "classic", "house", "baked", "individual",
        "gourmet", "white", "specialty", "with", "from", "that", "this", "iced",
        "small", "medium", "large", "market", "platter", "bags", "mixed",
        "natural", "served", "drink",
    }
)
BOLD_ITEM = re.compile(r"^-\s+\*\*(.+?)\*\*", re.MULTILINE)
MENU_DRINK = re.compile(r"^-\s+(.+?)(?:\s+\(|\s+is\s+an?\s)", re.MULTILINE)
PAREN = re.compile(r"\([^)]*\)")
H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", PAREN.sub("", name)).strip().lower()


def _names_with_tokens(name: str) -> set[str]:
    cleaned = _clean(name)
    names = {cleaned} if cleaned else set()
    for token in re.findall(r"[a-z]+", cleaned):
        if len(token) >= MIN_TOKEN_LENGTH and token not in GENERIC_WORDS:
            names.add(token)
    return names


def _add(lexicon: dict[str, set[str]], names: set[str], domain: str) -> None:
    for name in names:
        lexicon.setdefault(name, set()).add(domain)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _food_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in BOLD_ITEM.finditer(text):
        names |= _names_with_tokens(match.group(1))
    return names


def _menu_drink_names(text: str) -> set[str]:
    if DRINKS_HEADING not in text:
        return set()
    section = text.split(DRINKS_HEADING, 1)[1].split("\n## ", 1)[0]
    names: set[str] = {"oatmilk"}
    for match in MENU_DRINK.finditer(section):
        names |= _names_with_tokens(match.group(1))
    return names


def _file_names(path: Path) -> set[str]:
    names = {_clean(re.sub(r"[-_]+", " ", path.stem))}
    heading = H1.search(_read(path))
    if heading:
        names.add(re.sub(r"\s+(supplies|recipe)$", "", _clean(heading.group(1))))
    return {name for name in names if name}


def load_lexicon(data_dir: Path = DATA_DIR) -> Lexicon:
    """Item names found in the knowledge files; reads files."""
    lexicon: dict[str, set[str]] = {}
    _add(lexicon, _food_names(_read(data_dir / FOOD_FILE)), FOOD)
    _add(lexicon, _menu_drink_names(_read(data_dir / BEVERAGE_MENU_FILE)), BEVERAGE)
    for folder in BEVERAGE_DIRS:
        for path in sorted((data_dir / folder).glob("*.md")):
            _add(lexicon, _file_names(path), BEVERAGE)
    if (data_dir / NAPKIN_FILE).is_file():
        _add(lexicon, set(NAPKIN_NAMES), NAPKIN)
    return {name: frozenset(domains) for name, domains in lexicon.items()}

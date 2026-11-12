"""Finding the numbers a question contains, as digits or as words (spec 009 section 4.1 A)."""

from __future__ import annotations

import math
import re

_UNITS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()

WORD_NUMBERS: dict[str, int] = {word: value for value, word in enumerate(_UNITS)}
for _index, _ten in enumerate(_TENS):
    WORD_NUMBERS[_ten] = (_index + 2) * 10
    for _value, _unit in enumerate(_UNITS[1:10], start=1):
        WORD_NUMBERS[f"{_ten}-{_unit}"] = (_index + 2) * 10 + _value
        WORD_NUMBERS[f"{_ten} {_unit}"] = (_index + 2) * 10 + _value
WORD_NUMBERS["one hundred"] = 100
WORD_NUMBERS["hundred"] = 100

ALWAYS_ACCEPTED = 1.0
_DIGITS = re.compile(r"(?<!\d)\d+(?:,\d{3})*(?:\.\d+)?")
_WORDS = re.compile(
    r"(?<![a-z0-9-])("
    + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(WORD_NUMBERS, key=len, reverse=True))
    + r")(?![a-z0-9-])",
    re.IGNORECASE,
)


def numbers_in(question: str) -> set[float]:
    """Every number the question contains, as digits or as words from zero to one hundred."""
    if not isinstance(question, str):
        return set()
    found = {float(text.replace(",", "")) for text in _DIGITS.findall(question)}
    for match in _WORDS.finditer(question):
        found.add(float(WORD_NUMBERS[re.sub(r"\s+", " ", match.group(1).lower())]))
    return found


def as_number(value: object) -> float | None:
    """The number a value stands for (int, float, or numeric text), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(",", ""))
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None

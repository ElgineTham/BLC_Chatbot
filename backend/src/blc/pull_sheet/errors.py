"""Error type for the pull sheet."""

from __future__ import annotations


class BeoError(ValueError):
    """The BEO text is invalid."""

    def __init__(self, detail: str, line: int | None = None) -> None:
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{detail}")

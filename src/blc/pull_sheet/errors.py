"""Error types for the pull sheet."""

from __future__ import annotations

from pathlib import Path


class RuleFileError(ValueError):
    """The beverage menu or rules file is missing or invalid."""

    def __init__(self, path: Path, detail: str, line: int | None = None) -> None:
        self.path = path
        self.line = line
        where = f"line {line}: " if line is not None else ""
        super().__init__(f"{path}: {where}{detail}")


class BeoError(ValueError):
    """The BEO text is invalid."""

    def __init__(self, detail: str, line: int | None = None) -> None:
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{detail}")

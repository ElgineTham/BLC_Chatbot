"""Reading JSON rule files and shared validation helpers."""

from __future__ import annotations

import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

from blc.pull_sheet.errors import RuleFileError

_TAG_RE = re.compile(r"[A-Z0-9-]+")


def quote(key: str) -> str:
    """Object key in a location, with double quotes."""
    return '"' + key.replace('"', '\\"') + '"'


def is_number(value: Any) -> bool:
    return isinstance(value, (int, Fraction)) and not isinstance(value, bool)


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Checker:
    """Raises RuleFileError for one file, with entry locations."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def fail(self, where: str, msg: str) -> None:
        detail = f"{where}: {msg}" if where else msg
        raise RuleFileError(self.path, detail)

    def obj(
        self,
        where: str,
        value: Any,
        required: tuple[str, ...],
        optional: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            self.fail(where, "must be an object")
        for key in required:
            if key not in value:
                self.fail(where, f"missing key {key!r}")
        for key in value:
            if key not in required and key not in optional:
                self.fail(where, f"unknown key {key!r}")
        return value

    def array(self, where: str, value: Any) -> list[Any]:
        if not isinstance(value, list):
            self.fail(where, "must be an array")
        return value

    def text(self, where: str, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            self.fail(where, "must be a non-empty string")
        return value.strip()

    def tag(self, where: str, value: Any) -> str:
        if not isinstance(value, str):
            self.fail(where, "must be a tag string")
        if not _TAG_RE.fullmatch(value):
            self.fail(where, f"invalid tag {value!r} (use capitals A-Z, 0-9, -)")
        return value


def read_json(base_dir: Path, rel: str) -> tuple[Path, Any]:
    path = Path(base_dir) / rel
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuleFileError(path, "file not found") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise RuleFileError(path, f"cannot read file ({exc})") from None

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise RuleFileError(path, f"duplicate key {key!r}")
            out[key] = value
        return out

    def bad_constant(name: str) -> Any:
        raise RuleFileError(path, f"invalid number {name}")

    try:
        data = json.loads(
            text,
            parse_float=Fraction,
            parse_constant=bad_constant,
            object_pairs_hook=pairs,
        )
    except json.JSONDecodeError as exc:
        raise RuleFileError(path, f"invalid JSON ({exc.msg})", line=exc.lineno) from None
    except RecursionError:
        raise RuleFileError(path, "JSON nested too deeply") from None
    return path, data

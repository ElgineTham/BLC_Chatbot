"""Beverage pull sheet entry point and CLI (specs 002 and 003).

The code lives in src/blc/pull_sheet/; this file makes it importable,
re-exports the public interface and runs main().
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from blc.pull_sheet import *  # noqa: E402,F401,F403
from blc.pull_sheet import (  # noqa: E402
    DEFAULT_RULES_DIR,
    BeoError,
    RuleFileError,
    build_pull_sheet,
    format_pull_sheet,
    load_catalog,
    parse_beo,
)


def main(argv: list[str] | None = None) -> int:
    """CLI: pull_sheet.py BEO_FILE [--rules DIR]."""
    parser = argparse.ArgumentParser(description="Beverage pull sheet from a BEO.")
    parser.add_argument("beo_file", metavar="BEO_FILE", type=Path)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_DIR, metavar="DIR")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        text = args.beo_file.read_text(encoding="utf-8")
        catalog = load_catalog(args.rules)
        sheet = build_pull_sheet(catalog, parse_beo(text))
    except (RuleFileError, BeoError, OSError, UnicodeDecodeError) as exc:
        message = " ".join(str(exc).split())
        print(f"error: {message}", file=sys.stderr)
        return 1
    sys.stdout.write(format_pull_sheet(sheet))
    return 0


if __name__ == "__main__":
    sys.exit(main())

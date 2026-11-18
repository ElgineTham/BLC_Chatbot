"""Print the stage trace of one question through the chat flow (spec 011)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import chat  # noqa: E402
from blc.trace import format_trace, trace_to_dict  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace one question through the chat flow.")
    parser.add_argument("question")
    parser.add_argument("--history", metavar="PATH", help="JSON list of {role, content}")
    parser.add_argument("--generate", action="store_true", help="also make the final answer call")
    parser.add_argument("--json", action="store_true", help="print the trace as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = chat.start_stack(chat.build_store)
    if started is None:
        return 1
    llm, store = started
    history = json.loads(Path(args.history).read_text()) if args.history else []
    trace = chat.run_turn(store, llm, history, args.question, generate=args.generate)
    if args.json:
        print(json.dumps(trace_to_dict(trace), indent=2))
    else:
        print(format_trace(trace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

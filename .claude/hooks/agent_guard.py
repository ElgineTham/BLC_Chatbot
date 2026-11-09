#!/usr/bin/env python3
"""PreToolUse guard enforcing per-agent access boundaries.

Claude Code runs this before every matching tool call and pipes the call as JSON
on stdin. If the call comes from one of the team agents (identified by
`agent_type`), it is checked against that agent's deny lists. A blocked call
exits with code 2 and a reason on stderr. Anything else exits 0, so the normal
permission flow applies. The main session and other agents are not restricted.

Policy fields (all are deny lists; anything not listed is allowed):
  read_deny   paths the agent may not read or search (Read, Glob, Grep)
  write_deny  paths the agent may not change (Edit, Write, MultiEdit, NotebookEdit)
  bash_deny   shell rules: "*" blocks all shell use; other entries are regexes
              that block any matching command. Commands mentioning a path in
              read_deny or write_deny are blocked automatically.
  bash_only   optional single regex: the ONLY command shape allowed. Shell
              commands can't be made safe with deny rules alone, so this is the
              one exception, used for "may run pytest and nothing else".

Path entries are project-relative. A trailing "/" means a directory and
everything in it. "*" means every path.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()

READ_TOOLS = {"Read", "Glob", "Grep"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

PYTEST_ONLY = (
    r"^(PYTEST_DISABLE_PLUGIN_AUTOLOAD=1\s+)?(poetry\s+run\s+)?"
    r"(python3?\s+-m\s+)?pytest(\s[^;&|`$<>()\n]*)?$"
)

POLICIES: dict[str, dict] = {
    "planner": {
        # Designs and orchestrates; implementation and tests belong to other agents.
        "read_deny": [],
        "write_deny": ["scripts/", "tests/", "evals/", "data/", ".git/"],
        "bash_deny": [],
    },
    "developer": {
        "read_deny": ["tests/", "evals/"],
        "write_deny": ["tests/", "evals/", "docs/", "data/", ".claude/", ".git/", "CLAUDE.md"],
        "bash_deny": [r"\bpytest\b"],
    },
    "tester": {
        "read_deny": ["scripts/", "README.md", ".git/"],
        "write_deny": [
            "scripts/", "docs/", "evals/", "data/", ".claude/", ".git/",
            "CLAUDE.md", "README.md", "pyproject.toml", "poetry.lock",
            "poetry.toml", ".gitignore",
        ],
        "bash_deny": ["*"],
    },
    "test-evaluator": {
        "read_deny": ["scripts/", "README.md", ".git/"],
        "write_deny": ["*"],
        "bash_deny": ["*"],
    },
    "code-evaluator": {
        "read_deny": ["tests/", "evals/", ".git/"],
        "write_deny": ["*"],
        "bash_deny": ["*"],
    },
    "implementation-evaluator": {
        "read_deny": [],
        "write_deny": ["*"],
        "bash_only": PYTEST_ONLY,
    },
}


def block(reason: str) -> None:
    print(f"Blocked by agent_guard: {reason}", file=sys.stderr)
    sys.exit(2)


def rel(raw: str | None, cwd: str) -> str | None:
    """Project-relative POSIX path ("" = project root), or None if outside it."""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(cwd) / path
    try:
        result = path.resolve().relative_to(PROJECT).as_posix()
    except ValueError:
        return None
    return "" if result == "." else result


def denied(path: str, deny: list[str]) -> str | None:
    """The deny entry covering `path`, if any."""
    for entry in deny:
        if entry == "*":
            return entry
        if entry.endswith("/"):
            if path == entry.rstrip("/") or path.startswith(entry):
                return entry
        elif path == entry:
            return entry
    return None


def contains_denied(root: str, deny: list[str]) -> str | None:
    """A deny entry that lies inside the search root `root`, if any."""
    for entry in deny:
        if entry == "*" or root == "" or entry.startswith(root.rstrip("/") + "/"):
            return entry
    return None


def target_paths(tool: str, tool_input: dict, cwd: str) -> list[str | None]:
    """Every path a tool call touches. None = outside the project or unsafe."""
    if tool in {"Read", "Edit", "Write", "MultiEdit"}:
        return [rel(tool_input.get("file_path"), cwd)]
    if tool == "NotebookEdit":
        return [rel(tool_input.get("notebook_path"), cwd)]
    if tool == "Glob":
        base = tool_input.get("path") or cwd
        pattern = tool_input.get("pattern", "")
        if ".." in pattern or pattern.startswith("/"):
            return [None]
        # The fixed (non-wildcard) directory prefix of the pattern narrows the root.
        fixed = re.split(r"[*?\[{]", pattern, maxsplit=1)[0]
        fixed_dir = fixed.rsplit("/", 1)[0] if "/" in fixed else ""
        return [rel(os.path.join(base, fixed_dir), cwd)]
    if tool == "Grep":
        glob = tool_input.get("glob") or ""
        if ".." in glob or glob.startswith("/"):
            return [None]
        return [rel(tool_input.get("path") or cwd, cwd)]
    return []


def check_read(policy: dict, tool: str, paths: list[str | None]) -> None:
    deny = policy.get("read_deny", [])
    if not deny:
        return
    for path in paths:
        if path is None:
            block(f"{tool} must stay inside the project (no '..' or outside paths).")
        hit = denied(path, deny)
        if hit:
            block(f"you may not read '{path}' (denied: {hit}).")
        if tool in {"Glob", "Grep"}:
            inner = contains_denied(path, deny)
            if inner:
                block(f"{tool} on '{path or '.'}' would include '{inner}', which you "
                      f"may not read. Pass a narrower path.")


def check_write(policy: dict, tool: str, paths: list[str | None]) -> None:
    deny = policy.get("write_deny", [])
    for path in paths:
        if path is None:
            block(f"{tool} must stay inside the project.")
        hit = denied(path, deny)
        if hit:
            what = "anything" if hit == "*" else f"'{path}' (denied: {hit})"
            block(f"you may not change {what}.")


def mentions(command: str, entry: str) -> bool:
    name = re.escape(entry.rstrip("/"))
    return re.search(rf"(^|[\s/'\"=]){name}(/|\s|$|['\"])", command) is not None


def check_bash(policy: dict, command: str) -> None:
    stripped = command.strip()
    if "bash_only" in policy:
        if not re.match(policy["bash_only"], stripped):
            block("you may only run a single plain pytest command "
                  "(e.g. 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run pytest tests/...').")
        return
    rules = policy.get("bash_deny", [])
    if "*" in rules:
        block("you may not run shell commands.")
    for rule in rules:
        if re.search(rule, stripped, flags=re.IGNORECASE):
            block(f"this command is not allowed (matches '{rule}').")
    for entry in policy.get("read_deny", []) + policy.get("write_deny", []):
        if entry != "*" and mentions(stripped, entry):
            block(f"you may not touch '{entry}' from the shell.")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    policy = POLICIES.get(payload.get("agent_type") or "")
    if policy is None:
        return 0

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or str(PROJECT)

    if tool in READ_TOOLS:
        check_read(policy, tool, target_paths(tool, tool_input, cwd))
    elif tool in WRITE_TOOLS:
        paths = target_paths(tool, tool_input, cwd)
        check_write(policy, tool, paths)
        check_read(policy, "Read", paths)  # editing a file means seeing it
    elif tool == "Bash":
        check_bash(policy, tool_input.get("command", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

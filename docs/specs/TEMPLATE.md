# Spec NNN: <Feature name>

- **Status:** draft | approved
- **Date:** YYYY-MM-DD

## 1. Goal
What this change achieves and why, in 2–4 sentences.

## 2. Out of scope
What this spec deliberately does NOT cover.

## 3. Interface contract
Only the public surface that tests call. Tests are written blind against this, so it must be exact.
List, for each item:
- the module path (e.g. `scripts/chat.py`);
- the function name, arguments with types and defaults, and the return type;
- the errors it raises, and when;
- data types it takes or returns (classes, fields, enums);
- constants that tests compare against.

```python
# scripts/<module>.py
@dataclass(frozen=True)
class ExampleResult:
    value: str

def example(arg: str, k: int = 3) -> ExampleResult:
    """Raises ValueError if k < 1."""
```

Do NOT describe how it works: no algorithms, step orders, regexes or internal helpers.
Behaviour belongs in sections 4–6 as input → output examples (ACs and test cases); the developer decides how to achieve it.

CLI / env vars / files read or written, if any:
- ...

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| ... | ... | ... | ... |

## 5. Acceptance criteria
Numbered and testable, stated as observable behaviour (what goes in, what comes out or happens), not implementation.
Each one should imply at least a right case, a wrong case and, where applicable, a boundary case.
Quality requirements (speed, dependencies, code structure, which files may change) are ACs too.
Tag each AC with how it is verified: `unit` (the default, may be left off), `integration`, `eval` or `manual` (the planner checks it by reading the code).
- **AC-1:** ...
- **AC-2** *(manual)*: ...

## 6. Test cases
Concrete examples the planner already knows about, including the tricky ones. Tests must cover all of these; the tester may add more.
Group them into one subsection per **area**, agreed with the user while brainstorming (e.g. one area per path through the flow: TOOL, DOCS).
IDs are `<AREA>-n`. Keep each row to one line.

### 6.1 <AREA, e.g. TOOL>
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| TOOL-1 | ... | ... | AC-1 |

### 6.2 <AREA, e.g. DOCS>
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| DOCS-1 | ... | ... | AC-2 |

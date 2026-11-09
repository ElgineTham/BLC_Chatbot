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
Behaviour belongs in sections 4–6 as input → output examples; the developer decides how to achieve it.

CLI / env vars / files read or written, if any:
- ...

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| ... | ... | ... | ... |

## 5. Edge cases
Edge cases the planner already knows about, each with its expected result. Tests must cover all of these; the tester may add more.
- EC-1: ...

## 6. Acceptance criteria
Numbered and testable, stated as observable behaviour (what goes in, what comes out or happens), not implementation.
Each one should imply at least a right case, a wrong case and, where applicable, a boundary case.
- **AC-1:** ...
- **AC-2:** ...

## 7. Non-functional requirements
| ID | Requirement | How verified (unit / integration / eval / manual) |
|---|---|---|
| NFR-1 | ... | ... |

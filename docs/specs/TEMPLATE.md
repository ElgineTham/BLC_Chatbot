# Spec NNN: <Feature name>

- **Status:** draft | approved
- **Date:** YYYY-MM-DD

## 1. Goal
What this change achieves and why, in 2–4 sentences.

## 2. Out of scope
What this spec deliberately does NOT cover.

## 3. Interface contract
The exact public surface. Tests are written ONLY against this, so it must be precise.
For each item: module path, name, signature with types, return type, raised errors.

```python
# scripts/<module>.py
def example(arg: str, k: int = 3) -> list[str]:
    """Raises ValueError if k < 1."""
```

CLI / env vars / files read or written, if any:
- ...

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| ... | ... | ... | ... |

## 5. Workflows
Step-by-step flows, including intermediate states.
1. ...
2. ...

## 6. Non-functional requirements
| ID | Requirement | How verified (unit / integration / eval / manual) |
|---|---|---|
| NFR-1 | ... | ... |

## 7. Known edge cases
Edge cases the planner already knows about. Tests must cover all of these; the tester may add more.
- EC-1: ...

## 8. Acceptance criteria
Numbered and testable. Each one should imply at least a right case, a wrong case and, where applicable, a boundary case.
- **AC-1:** ...
- **AC-2:** ...

## 9. Test layers
- **Unit:** Ollama and Chroma mocked/faked; deterministic; always run.
- **Integration:** real Ollama/Chroma; `@pytest.mark.integration`; skipped if Ollama is unavailable.
- **Eval:** golden-set quality metrics with thresholds; `@pytest.mark.eval`.

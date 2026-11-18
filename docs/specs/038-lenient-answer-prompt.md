# Spec 038: Lenient answer prompt for Gemini

- **Status:** approved (done: closed by the user on 2026-11-18 after manual testing; AC-1 to AC-4 verified, with all 24 unit tests passing; AC-5/AC-6 graded eval not run, because the Ollama judge was down)
- **Date:** 2026-11-18

## 1. Goal
The answer prompt was written to hold back `qwen2.5:7b`. On `gemini-3.5-flash-lite` (spec 037) it makes the model quote a rule line instead of answering. For example, "Do we need creamer for hot tea?" gets the creamer rule but no "No", and "What do we need to bring for bagels?" lists only the cream cheese and leaves out the bagels. This experiment replaces `FLOW_ANSWER_PROMPT` with a shorter, more lenient prompt. It keeps the answer simple and grounded, starts yes/no answers with Yes or No, invents no numbers and keeps the information complete. It also adds golden cases for both bugs to the food-answer eval (spec 027) so the experiment can be measured.

## 2. Out of scope
- The planner prompts, tool texts, tool pass-through and `fixed_reply` (spec 023); retrieval; the model or its temperature.
- Code-based "what to bring" answers.
- Changing `MIN_PASS_RATE` or the judge.
- Spec 023 AC-9's wording requirements are replaced by AC-1 to AC-3 of this spec. Its "simple / straightforward / grounded" word check (DOCS-3) stays and must still pass.

## 3. Interface contract
```python
# backend/src/blc/flow/reply.py  (exported from blc.flow, unchanged name)
FLOW_ANSWER_PROMPT: str = """You are Bay Laurel Catering's internal assistant for employees.
Answer the question from the documents shown. Other parts of the user's request are answered elsewhere; do not mention them.
Keep the answer simple, straightforward and grounded in the documents.
For a yes or no question, start the answer with "Yes" or "No".
Keep the information complete: include everything the documents say that answers the question, such as items that go together.
Don't invent numbers.
If the documents do not cover the question, say you don't know.
Cite the source paths of the documents you used."""
```
Nothing else in the public surface changes. How the answer model is called (first message `SystemMessage(FLOW_ANSWER_PROMPT)`, one `stream` call) is unchanged from spec 023.

**Golden file (planner data, spec 027 format):** `evals/answers/food_answers.jsonl` gains the cases in 6.2. The total stays within spec 027 AC-1's limit of 20 to 40 turns.

## 4. Inputs and outputs
| Input | Type / format | Valid range | Output / effect |
|---|---|---|---|
| question + retrieved documents | str + chunks | any | answer text streamed from the model under the new system prompt |

## 5. Acceptance criteria
- **AC-1:** `FLOW_ANSWER_PROMPT` equals the text in section 3 exactly.
- **AC-2:** `FLOW_ANSWER_PROMPT` still contains "simple", "straightforward" and "grounded" (any case). It does not contain `NO_INVENTED_RULE` (spec 021).
- **AC-3:** The answer call is unchanged: its first message is `SystemMessage(content=FLOW_ANSWER_PROMPT)`, with exactly one `stream` call per turn that has documents.
- **AC-4** *(manual)*: Only `backend/src/blc/flow/reply.py` changes in `backend/src/`. No other prompt, constant or flow code is touched.
- **AC-5** *(eval)*: Each new `must_pass` case in 6.2 passes every turn.
- **AC-6** *(eval)*: The food-answer eval still meets `MIN_PASS_RATE` (0.90) and every existing `must_pass` case passes. This includes the abstain cases (`abstain-cupcakes`, `abstain-oat-milk`): the lenient prompt must still say "don't know" instead of guessing "No".

## 6. Test cases
### 6.1 PROMPT
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| PROMPT-1 | import `FLOW_ANSWER_PROMPT` | equals section 3 text | AC-1 |
| PROMPT-2 | lowercased prompt | contains "simple", "straightforward", "grounded"; contains `"yes" or "no"`; contains "don't invent numbers"; contains "don't know" | AC-1, AC-2 |
| PROMPT-3 | prompt vs `NO_INVENTED_RULE` | rule string not in prompt | AC-2 |
| PROMPT-4 | planned turn with one search that returns docs (faked LLM) | one `stream` call; first message is `SystemMessage(FLOW_ANSWER_PROMPT)` | AC-3 |

### 6.2 EVAL (new golden cases, `must_pass` true)
| ID | Input / situation | Expected | Covers |
|---|---|---|---|
| EVAL-1 | `creamer-hot-tea`: "Do we need to bring creamer for hot tea?" | Required: starts with No; creamer is only for coffee or decaf. Must not: say yes or tell them to bring creamer for tea. | AC-5 |
| EVAL-2 | `bagels-bring-what`: "What do we need to bring for bagels?" | Required: the assorted bagels (metal rack in the service room, near the manager's table) and the cream cheese (service cooler). Must not: leave out the bagels, or add plant-based herb cream cheese as a bagel item. | AC-5 |
| EVAL-3 | `conv-creamer-followup`: turn 1 "Do we need creamer for coffee?" then turn 2 "What about hot tea?" | turn 1 Required: Yes. Turn 2 Required: No, creamer is only for coffee or decaf. | AC-5 |
| EVAL-4 | full food-answer eval | pass rate ≥ 0.90; all `must_pass` cases pass, including both abstain cases | AC-6 |

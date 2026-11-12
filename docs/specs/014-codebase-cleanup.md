# Spec 014: Codebase cleanup (remove dead code and its tests)

- **Status:** approved (done)
- **Date:** 2026-11-12

## 1. Goal
Remove code that the chatbot no longer runs, and the tests, stubs and stray files that only exist for it. A reachability scan from the entry points (`scripts/chat.py`, `voice_chat.py`, `ingest.py`, `pull_sheet.py`, `trace_flow.py`) found three groups of dead code, left behind by specs 006 to 013:
1. **the old JSON router** (replaced by `route_fast`, spec 013);
2. **the old chat-flow functions** (replaced by `run_stages` / `run_turn`, spec 011);
3. **a few unused names and stray files**.
Removing the second group also lets the five spec 001 `answer_turn` tests (which fail because they patch functions the flow no longer calls) be rewritten onto the real flow, so the "known failures" list shrinks.

Behaviour must not change: the chatbot, the trace CLI, the router eval (31 of 31) and every test that remains must work as before.

## 2. Out of scope
- `src/blc/judge/` (eval-only today, needed by the answer evals and by spec 012): **kept**.
- `src/blc/pull_sheet/`, `src/blc/tools/`, `src/blc/tool_step/`, `src/blc/trace/`, voice code other than `normalize_command`, `scripts/ingest.py`, the knowledge under `data/`, `evals/retrieval/golden.jsonl`.
- Constants that tests compare against and that cost nothing (`ROUTES`, `ROUTE_KINDS`, `BEV_STATUSES`, `STAGE_NAMES`) and the `unfaithful` field of `RouteDecision`: **kept**.
- Removing unused third-party dependencies (§4.4): needs `poetry lock` and the network; listed, not done here.
- Changing any spec file's text, except the "superseded" notes in §4.5.

## 3. Interface contract
No new public interface. After the cleanup these names must **still exist and work** (tests and the flow use them): `route_fast`, `split_clauses`, `is_follow_up`, `quick_label`, `TOOL_REGISTRY`, `pick_tool`, `classifier_prompt`, `RoutedPart`, `RouteDecision`, `kind_of`, `ROUTES`, `ROUTE_KINDS`, `pull_sheet_items_in`, `PULL_SHEET_ITEMS`; in `scripts/chat.py`: `run_turn`, `run_stages`, `answer_turn`, `retrieve`, `run_tool_step`, `run_part`, `build_final_messages`, `summarize_if_long`, `summarize_history`, `CHAT_MODEL`, `CHAT_KEEP_ALIVE`, `CHAT_TEMPERATURE`, `TOOL_PROMPT`, `ANSWER_PROMPT`, `CHAT_TOOLS`, `main`. The names listed in §4.1 to §4.3 must **no longer exist** in the code, and nothing may import them.

## 4. What is removed

### 4.1 Group 1: the old JSON router (code, `src/blc/router/`)
Delete these modules, and remove their names from `src/blc/router/__init__.py`:
- `route.py` (`route_question`), `faithful.py` (`route_faithfully`), `fidelity.py` (`check_fidelity`, `FIDELITY_PREFIX` and helpers), `parsing.py` (`parse_reply` and helpers), `prompt.py` (`ROUTER_PROMPT`, `ROUTER_SCHEMA`, `build_router_messages` and helpers), `drinks.py` (`MENU_DRINKS`, `menu_drinks_in`: used only by the fidelity check).
Keep `decision.py`, `items.py`, `clauses.py`, `labels.py`, `registry.py`, `fast.py`. If a kept module imports something from a deleted one (for example `kind_of` or a number helper), move that one small function into the module that uses it, or into `decision.py`, without changing its behaviour.

### 4.2 Group 1: the old router's tests (`tests/router/`)
Delete: `test_router_parsing.py`, `test_router_reading.py`, `test_router_faithful.py`, `test_router_fidelity.py`, `test_router_drinks.py`, `test_router_eval.py` (the old router's eval), `test_flow_fidelity.py` (the emptied stub), and any fixture or case list in `conftest.py` that only they use. **Keep** `test_router_items.py`, `test_clauses.py`, `test_registry.py`, `test_route_fast.py`, `test_route_fast_flow.py`, `test_fast_router_eval.py`. If a kept test imports a name from a deleted module, move the needed helper into the test's own `conftest.py`.

### 4.3 Group 2: the old chat-flow functions (code, `scripts/chat.py`, `scripts/voice_chat.py`)
Delete from `chat.py`: `answer_from_context`, `answer_with_tools`, `ToolAnswer`, `maybe_summarize` and the alias `SYSTEM_PROMPT`; and any helper that only they used. Delete `normalize_command` from `voice_chat.py` (unused; `is_exit_command` does the work). Delete `MAX_PROMPT_CHARS` from `registry.py` (unused).

Their tests move onto the real flow **without weakening any assertion**:
- `tests/router/test_answer_flow.py` (it calls `answer_with_tools`): rewrite to call `run_turn(..., generate=True)` with a fake store, keeping each assertion (the tool loop, retries, rounds, fallback, the final-message contents). Tests that `tests/flow/` already cover with the same assertion may be dropped.
- `tests/test_voice_io_answer_turn.py` (the five failing `answer_turn` tests) and `tests/test_voice_io.py`: rewrite the `answer_turn` tests to script a fake model through the real flow instead of patching `answer_from_context` and `maybe_summarize`; delete the tests of `normalize_command`.
- `tests/beverage_knowledge/test_generation.py` and `test_generation_eval.py` (spec 004), `tests/bev_tools/test_answer_loop.py`, `test_answer_eval.py`, `test_tool_choice_eval.py` (spec 005): switch every call of the deleted functions to `run_turn(store, llm, history, question).reply` (or `.tools`, `.route` where they read tool calls). **`test_generation_eval.py` must be marked `eval`** (it runs the real model and is not marked today).

### 4.4 Group 3: stray files and optional dependencies
- Delete `.DS_Store` files from the repository tree (they are untracked) and add `.DS_Store` to `.gitignore`.
- **Not done here (needs your decision):** `pyproject.toml` lists `pypdf`, `python-dotenv` and `langchain-community`, which nothing imports; `ollama`, `langchain` and `chromadb` are pulled in by `langchain-ollama` and `langchain-chroma`. Removing them needs `poetry lock`.

### 4.5 Notes (planner)
The planner marks specs 006, 007 and 010 "superseded in part by spec 013" and updates the layout in `CLAUDE.md` and `README.md` after the cleanup.

## 5. Edge cases
- EC-1: no file under `src/`, `scripts/` or `tests/` imports a deleted module or name (the developer and tester each check their side with a search and report it).
- EC-2: `blc.router` still exports every name §3 lists, and `from blc.router import RouteDecision, RoutedPart` works.
- EC-3: `import chat` and `import voice_chat` and `import trace_flow` succeed (no leftover import of a deleted name).
- EC-4: a function that a deleted function used and that something else also uses is **not** deleted.
- EC-5: where a test is rewritten onto `run_turn`, it needs a fake store with `similarity_search(query, k=...)` and the scripted model of the flow tests; the expected replies come from the letter router (spec 013).
- EC-6: a rewritten test scripts **exactly** the model calls the real flow makes, in order: a summary call first if the history is long enough to be summarised; then, **only if the question has a number or a pull sheet item word** (spec 013 §4.3, `quick_label`), one letter reply for the router (`D`, `T`, or one letter per part sent); then the final answer. A question such as "Where is sugar?" contains an item word, so its test needs a router letter; "Where is the coffee?" does not. A scripted model that runs out of replies is a test bug.
- EC-7: no unused class or fixture is left behind in `tests/router/conftest.py` or `tests/flow/conftest.py` (for example `RouterFake` and `jparts`) once the tests that used them are gone; the tester checks each with a search.

## 6. Acceptance criteria
- **AC-1 (nothing dead is left):** after the cleanup, the reachability scan over `src/` and `scripts/` (names not reachable from the entry points) lists nothing except the kept names of §2 (`judge`, the compared constants, `unfaithful`).
- **AC-2 (tests):** the unit layer (`-m "not integration and not eval"`) passes with **no failures** except spec 001's `test_constants_match_contract`, if it still fails. Every rewritten test follows EC-6. The five `answer_turn` tests and `test_generation_eval.py` (now marked `eval`) no longer fail in the unit layer.
- **AC-3 (behaviour unchanged):** the router eval `tests/router/test_fast_router_eval.py` still gives 31 of 31 with the same decisions; the planner runs `trace_flow.py` on a DOCS, a TOOL and a BOTH question and sees the same stages as before.
- **AC-4 (smaller):** the number of Python files and lines under `src/blc/router/`, `scripts/chat.py` and `tests/router/` goes down; the implementation-evaluator reports the before and after counts.
- **AC-5 (no weakened tests):** every assertion of a rewritten test still exists in a test of the new flow; the tester lists, for each rewritten file, the tests that were dropped as duplicates and where their assertion is now covered.

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | No behaviour change; no new dependency. | manual (review) + AC-3 |
| NFR-2 | Nothing is deleted that a kept module, a kept test or an entry point still uses. | unit (the whole suite) + the scan of AC-1 |
| NFR-3 | The cleanup is split by owner: the developer edits `src/` and `scripts/`, the tester edits `tests/`, and neither sees the other's list beyond this spec. | manual |

## Closure note (2026-11-12)
Done. Verified: unit layer 2174 passed, 1 failed (the known spec 001 voice constant `test_constants_match_contract`); router eval 31 of 31; `tool_step` eval 28 of 28; reachability scan lists only the kept names (the `judge` package and the compared constants `ROUTES`, `ROUTE_KINDS`, `BEV_STATUSES`, `STAGE_NAMES`); trace CLI checked on a DOCS, a TOOL and a BOTH question. Removed: six old router modules (387 lines), the old chat-flow functions and their tests, the five spec 001 `answer_turn` failures (rewritten onto the real flow), `test_generation_eval.py` is now marked `eval`.
- **Left for you:** seven emptied test files in `tests/router/` that collect nothing and can be deleted by hand (`test_router_parsing.py`, `test_router_reading.py`, `test_router_faithful.py`, `test_router_fidelity.py`, `test_router_drinks.py`, `test_router_eval.py`, `test_flow_fidelity.py`); the unused dependencies `pypdf`, `python-dotenv` and `langchain-community` (§4.4).
- **Not caused by this spec, still open:** three real-model generation cases (`lemonade-scale-5gal`, `oos-flour`, `oos-ice-machine`), and the retrieval findings E2 and E21 of spec 011.

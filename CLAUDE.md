<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

# Stock AI — Technical Standards & Enforcement

This document defines the **Law of the Land** for the Stock AI project. Adherence to these standards is mandatory for all changes. Do not prioritize "working code" over "correct architecture."

## 1. The Pipeline Laws (Backend)

The daily research pipeline is the core of this system. It must be resilient, resumable, and traceable.

*   **Idempotency or Death:** Every pipeline stage (Tier 1, Scoring, Backtest, etc.) MUST be idempotent. Running a stage twice should never duplicate data or leave the DB in an inconsistent state.
*   **Checkpointing:** New sub-tasks within the pipeline must use the `PipelineCheckpoint` system. They must be able to resume from the last successful symbol after a crash.
*   **The NSE Suffix:** All Indian stock symbols MUST have the `.NS` suffix. Never use raw symbols (e.g., `RELIANCE`) in database queries or API logic.
*   **Timezone Integrity:**
    - Internal processing and DB storage: `UTC`.
    - Display and Indian Market logic: `Asia/Kolkata` (IST).
    - Always use `datetime.now(datetime.timezone.utc)` for timestamps.
*   **Error Classification:** Use the `classify_error` utility for all pipeline failures. Log specific symbol failures to `PipelineError` table; do not let a single stock failure crash the entire run.
*   **Concurrency Guard:** Never start a pipeline run or backtest if one is already `running`. Use `cleanup_zombie_runs` to handle crashed processes on startup.

## 2. Data Integrity & Schema

*   **Migrations are Holy:** Direct DB manipulation is forbidden. Every schema change (even adding an index) MUST have an Alembic migration.
*   **SQLAlchemy Only:** No raw SQL strings unless explicitly approved for performance-critical bottlenecks. Use the ORM or the Core expression language.
*   **Pydantic Enforcement:** All API endpoints must use Pydantic models for both Input (Request) and Output (Response) validation. No `dict` passing.

## 3. Frontend Architecture

*   **No Raw State Manipulation:** Use `lodash/fp` (map, filter, reduce) for all data transformations. Never mutate props or state directly.
*   **Component Purity:** Components should be "dumb" display units where possible. Complex logic (TA calculations, ranking) belongs in the Backend.
*   **Theme Consistency:** Adhere strictly to the Tailwind color palette. Custom CSS is a last resort.
*   **UX Response:** Long-running actions (Triggering pipeline, starting backtest) must have immediate UI feedback (Loaders, Toast notifications).

## 4. Python Environment

*   **Never create a new venv.** The project venv lives at `backend/venv/`. It is the only venv for this project.
*   **Always use it:** run scripts as `backend/venv/bin/python <script>` or activate first with `source backend/venv/bin/activate`.
*   **Never run** `python -m venv`, `virtualenv`, or `uv venv` — if the interpreter or a package seems missing, ask Arafat instead of creating a new environment.

## 5. Testing & Verification

*   **Regression First:** Every bug fix must include a `pytest` case that reproduces the failure.
*   **Mocking External APIs:** Never run tests against live `yfinance` or NSE servers. Use `unittest.mock` or `pytest-mock` to provide consistent fixtures.
*   **CI Cleanliness:** Tests must pass before any feature is considered "done."

---

---

## Building and Running

### Local Development (Docker)
1. Run `docker-compose up -d` to spin up PostgreSQL (port 5434) and Redis (port 6380).

### Backend Setup
1. `cd backend/`
2. `pip install -r requirements.txt`
3. `alembic upgrade head`
4. `uvicorn app.main:app --reload`
   - **Pro Tip:** For parallel backtesting (e.g., when running `parameter_sweep.py`), use multiple workers to bypass the GIL: `uvicorn app.main:app --workers 4`
5. Start Worker: `celery -A app.core.celery_app worker --loglevel=info`

### Frontend Setup
1. `cd frontend/`
2. `npm install`
3. `npm run dev`

## Operating Principles

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work.

### Rule 0 — Greet me first
Always start your responses by mentioning my name 'Arafat' first.

### Rule 1 — Think Before Coding
State assumptions explicitly. Ask rather than guess.
Push back when a simpler approach exists. Stop when confused.

### Rule 2 — Simplicity First
Minimum code that solves the problem. Nothing speculative.
No abstractions for single-use code.

### Rule 3 — Surgical Changes
Touch only what you must. Don't improve adjacent code.
Match existing style. Don't refactor what isn't broken.

### Rule 4 — Goal-Driven Execution
Define success criteria. Loop until verified.
Strong success criteria let Claude loop independently.

### Rule 5 — Use the model only for judgment calls
Use for: classification, drafting, summarization, extraction.
Do NOT use for: routing, retries, deterministic transforms.
If code can answer, code answers.

### Rule 6 — Token budgets are not advisory
Per-task: 4,000 tokens. Per-session: 30,000 tokens.
If approaching budget, summarize and start fresh.
Surface the breach. Do not silently overrun.

### Rule 7 — Surface conflicts, don't average them
If two patterns contradict, pick one (more recent / more tested).
Explain why. Flag the other for cleanup.

### Rule 8 — Read before you write
Before adding code, read exports, immediate callers, shared utilities.
If unsure why existing code is structured a certain way, ask.

### Rule 9 — Tests verify intent, not just behavior
Tests must encode WHY behavior matters, not just WHAT it does.
A test that can't fail when business logic changes is wrong.

### Rule 10 — Checkpoint after every significant step
Summarize what was done, what's verified, what's left.
Don't continue from a state you can't describe back.

### Rule 11 — Match the codebase's conventions, even if you disagree
Conformance > taste inside the codebase.
If you think a convention is harmful, surface it. Don't fork silently.

### Rule 12 — Fail loud
"Completed" is wrong if anything was skipped silently.
"Tests pass" is wrong if any were skipped.
Default to surfacing uncertainty, not hiding it.

# CURRENT_STATE.md — FBF UI Project State

## Repository State

| Property | Status |
|----------|--------|
| Package Version | `0.1.0` |
| Active Phase | `P8 — SQLite Database Browser & Persistence` |
| Phase State | `PHASE P8 IMPLEMENTATION COMPLETE — AWAITING AUTHORIZATION` |
| Core Dependency | `fbf-core 0.1.0` (editable sibling dependency) |
| Dedicated Venv | `/mnt/datos/workspace/fbf/fbf-ui/.venv` |
| Quality Gates | All passing (`ruff`, `mypy --strict`, `pytest`, boundary contracts) |

---

## Completed Milestones & Phases

- [x] **P0 — Repository Architecture & Investigation**: Evaluated stack options, established dependency strategy, defined layer boundaries, produced capability matrix and visualization catalog.
- [x] **P1 — Project Bootstrap & Tooling** (Frozen at commit `5009989`): Created `fbf-ui` package, set up setuptools configuration, dedicated `.venv`, FastAPI app shell, health endpoint reporting installed `fbf-core` version, contract tests, and documentation.
- [x] **P2 — Application Shell & UI Presentation Foundation** (Frozen at commit `5d7cd2c`): Built Jinja2 presentation templates (`base.html`, `dashboard.html`, `study.html`, `run.html`, `results.html`, `compare.html`, `persistence.html`), static dark theme CSS (`/static/css/app.css`), package-relative path resolution, active tab navbar highlighting, template unit tests, and scaffolding placeholders.
- [x] **P3 — YAML Import & File Workflows** (Frozen at commit `55910c9`): REST API endpoints for YAML upload, parse-path, parse-text; `StudyConfigDTO`; workspace path security boundary; HTTP contract tests; ADR 003 updated.
- [x] **P4 — Configuration Validation & DTO Mapping** (Frozen at commit `55910c9`): REST API `/api/v1/study/validate` endpoint; validation error mapping and structured configuration DTO adapter.
- [x] **P5 — Structured Configuration Editor UI** (Frozen at commit `55910c9`): Form-based parameter editor with live validation feedback; two-way synchronization between structured UI fields and canonical YAML.
- [x] **P6 — Study Plan Dry Run & Preview** (Frozen at commit `91d1c27`): REST API `/api/v1/study/preview` endpoint; `StudyPlanPreviewDTO`; preview panel in structured editor.
- [x] **P7 — Non-Persistent Simulation Execution & Progress Engine** (Frozen at commit `fefbbb3`): Execution state machine engine, background simulation runner, real-time progress polling, best-effort cancellation, in-memory result storage.

---

## Active Phase: P8 — SQLite Database Browser & Persistence

### Status
Implementation and quality gate validation are **complete**. Working tree is ready for final pre-commit verification.
Awaiting explicit user authorization before creating the single atomic commit for Phase P8.

### Implemented in P8

**Core Repository (fbf-core):**
- `SQLiteRepository.list_experiments_with_plans()` — Joins experiments with their latest plan metadata (status, unit_count) using a windowed subquery. Experiments without plans return `status=None, unit_count=None`.
- `SQLiteRepository.list_plans_for_experiment(experiment_id)` — Returns lightweight plan summaries (plan_id, created_at, unit_count, status) without reconstructing `ResearchPlan`.
- `SQLiteRepository.get_experiment_metadata(experiment_id)` — Returns experiment metadata without requiring `PersistenceReconstructionContext`.
- `SQLiteRepository.get_execution_result_metadata(plan_id)` — Returns execution result summary (result_id, executed_at, duration_seconds, success/failure counts, success_rate) without loading simulation timelines.
- 19 new Core repository tests covering all new methods.

**UI Orchestration (fbf-ui):**
- `PersistenceService` expanded with `list_experiments()`, `get_experiment_detail()`, `get_plan_result_summary()` methods.
- DTOs: `ExperimentSummaryDTO`, `ExperimentDetailDTO`, `PlanSummaryDTO`, `ResultSummaryDTO`.
- Status normalization: `None`/`"planned"` → `"pending"` (consistent with CLI convention).
- 13 PersistenceService unit tests.

**UI API (fbf-ui):**
- `GET /api/v1/persistence/experiments` — List all experiments with status and unit count.
- `GET /api/v1/persistence/experiments/{experiment_id}` — Experiment detail with plans.
- `GET /api/v1/persistence/experiments/{experiment_id}/plans` — List plans for an experiment.
- `GET /api/v1/persistence/plans/{plan_id}/results` — Execution result summary.
- 8 API tests with proper error handling (404 for missing resources).

**UI Presentation (fbf-ui):**
- `/persistence` — Experiment list browser with table display, status badges, and links to detail.
- `/persistence/experiments/{experiment_id}` — Experiment detail page with metadata and plans table.
- Dark theme consistent with existing pages.
- Client-side JavaScript for API consumption.
- 2 new presentation tests (9 total).

### Architecture Decisions (P8)
- **Read-only browser**: P8 does not write to SQLite. All data comes from existing Core persistence.
- **No arbitrary database paths**: Database path is configured at application level, not per-request.
- **All SQL in Core**: UI/API/presentation layers never import `sqlite3` or execute SQL.
- **Lightweight queries**: New repository methods avoid full domain object reconstruction.
- **Result metadata**: `get_execution_result_metadata()` provides summary without loading simulation timelines.

### Core APIs Consumed
- `list_experiments_with_plans()` — Browser list query.
- `list_plans_for_experiment()` — Plan enumeration.
- `get_experiment_metadata()` — Lightweight metadata.
- `get_execution_result_metadata()` — Result summary.
- `find_result_by_plan()` — Result existence check.
- `create_study_repository()` — Repository factory.

### Core Modification Status
**Core was modified** with 4 new repository methods. All methods are backward-compatible additions. Existing methods unchanged.

### CLI Status
**CLI was untouched.** P8 is a UI-only feature. The CLI could optionally adopt the new repository methods in the future.

---

## Frozen Architectural Decisions

1. **Technology Stack**: FastAPI + Pydantic v2 + Uvicorn HTTP server with initial server-rendered presentation, preserving a clean REST API seam for future SPA integration (ADR 001).
2. **Dependency Boundary**: `fbf-ui` depends directly on `fbf-core` (Tier 1 & Tier 2). No imports or subprocess calls to `fbf-cli` (ADR 002).
3. **File Handling & Path Security**: Explicit distinction between browser uploads, server filesystem references, persisted configs, and SQLite database paths. Server path references MUST resolve within configured `workspace_root` (ADR 003).
4. **Configuration Adapter**: `fbf-core`'s `StudyConfiguration` is the canonical source of truth, adapted via UI DTOs (ADR 004).
5. **Visualization Pipeline**: Financial metrics computed in Core; UI transforms execution results into visualization view models (ADR 005).

---

## Next Steps

1. Await explicit user commit authorization for Phase P8.
2. After P8 commit, update this file to reflect `COMPLETE`.
3. Proceed to **P9 — Persistent Simulation Logging** (execution result persistence).

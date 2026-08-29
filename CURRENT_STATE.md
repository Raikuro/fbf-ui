# CURRENT_STATE.md — FBF UI Project State

## Repository State

| Property | Status |
|----------|--------|
| Package Version | `0.1.0` |
| Active Phase | `P7 — Simulation Execution` |
| Phase State | `PHASE P7 READY FOR COMMIT — AWAITING AUTHORIZATION` |
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

---

## Active Phase: P7 — Simulation Execution

### Status
Implementation and quality gate validation are **complete**. Working tree is ready for final pre-commit verification.
Awaiting explicit user authorization before creating the single atomic commit for Phase P7.

### Implemented in P7
- `src/fbf/ui/orchestration/execution_service.py` — `submit_built_study()` method accepting pre-built `BuiltStudy`; `_results` dict for storing `ResearchExecutionResult`; `get_result()` method.
- `src/fbf/ui/api/run.py` — `POST /api/v1/run/execute-config` endpoint accepting `StudyConfigDTO`; DTO-based execution path using same conversion as preview.
- `src/fbf/ui/presentation/templates/study/edit.html` — Execute button, execution status panel, progress polling, and cancel button integrated into the structured editor.
- `src/fbf/ui/presentation/templates/run.html` — Job lookup monitoring page replacing previous placeholder.
- `tests/unit/test_execution_service.py` — Tests for `submit_built_study()`, result storage on completion/failure/cancellation (6 new tests).
- `tests/unit/test_run_api.py` — HTTP contract tests for execute-config endpoint (3 new tests).

### Architecture Decisions (P7)
- **Plan rebuild during execution**: The editor sends the same `StudyConfigDTO` to both preview and execution. Both paths use `config_dto_to_canonical_dict()` → `StudyConfiguration.from_yaml()` → `build_study_plan()`. This guarantees configuration identity without server-side session state.
- **Result storage**: `ResearchExecutionResult` (frozen, immutable) stored in-memory keyed by job_id. Available for P8 consumption.
- **Cancellation semantics preserved**: Best-effort only — Core cannot be interrupted. Results discarded on cancellation. Existing state machine transitions unchanged.
- **initial_wealth consistency**: Both preview and execution use the same hardcoded default `Money(Decimal("1000000.00"), Currency.EUR)`.

### Core APIs Consumed
- `build_study_plan()` — Builds `BuiltStudy` from `StudyConfiguration`.
- `execute_study_plan()` — Executes the built study plan with `ExecutionOptions`.
- `BuiltStudy` — Pre-built study plan container.
- `ExecutionOptions` — Execution configuration including progress callback.
- `ResearchExecutionResult` — Immutable execution result (stored for P8).

### Core Modification Status
**No Core modifications were required.** All P7 functionality uses the existing public Core API.

### CLI Status
**CLI was untouched.** P7 is a UI-only feature.

---

## Frozen Architectural Decisions

1. **Technology Stack**: FastAPI + Pydantic v2 + Uvicorn HTTP server with initial server-rendered presentation, preserving a clean REST API seam for future SPA integration (ADR 001).
2. **Dependency Boundary**: `fbf-ui` depends directly on `fbf-core` (Tier 1 & Tier 2). No imports or subprocess calls to `fbf-cli` (ADR 002).
3. **File Handling & Path Security**: Explicit distinction between browser uploads, server filesystem references, persisted configs, and SQLite database paths. Server path references MUST resolve within configured `workspace_root` (ADR 003).
4. **Configuration Adapter**: `fbf-core`'s `StudyConfiguration` is the canonical source of truth, adapted via UI DTOs (ADR 004).
5. **Visualization Pipeline**: Financial metrics computed in Core; UI transforms execution results into visualization view models (ADR 005).

---

## Next Steps

1. Await explicit user commit authorization for Phase P7.
2. After P7 commit, update this file to reflect `COMPLETE`.
3. Request planning approval for **P8 — SQLite Database Browser**.

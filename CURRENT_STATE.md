# CURRENT_STATE.md — FBF UI Project State

## Repository State

| Property | Status |
|----------|--------|
| Package Version | `0.1.0` |
| Active Phase | `P6 — Study Plan Dry Run & Preview` |
| Phase State | `PHASE P6 READY FOR COMMIT — AWAITING AUTHORIZATION` |
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

---

## Active Phase: P6 — Study Plan Dry Run & Preview

### Status
Implementation and quality gate validation are **complete**. Working tree is ready for final pre-commit verification.
Awaiting explicit user authorization before creating the single atomic commit for Phase P6.

### Implemented in P6
- `src/fbf/ui/orchestration/study_service.py` — `StudyPlanPreviewDTO`, `ParameterAxisDTO`, `StudyService.preview_study_plan()` method.
- `src/fbf/ui/api/study.py` — `POST /api/v1/study/preview` endpoint returning detailed study plan preview.
- `src/fbf/ui/presentation/templates/study/edit.html` — Preview button and panel integrated into the structured editor.
- `tests/unit/test_study_service.py` — Tests for preview DTO, service method, and field validation.
- `tests/unit/test_study_preview_api.py` — HTTP contract tests for preview endpoint (6 tests).

### Core APIs Consumed
- `build_study_plan()` — Returns `BuiltStudy` with plan, experiment definition, cohorts, and parameter configurations.
- `StudyConfiguration.from_yaml()` — Parses canonical configuration dict.
- `Money` — Initial wealth representation.
- `CohortSpecification.start_date` — Cohort date range extraction.
- `ParameterConfiguration.values` — Parameter axis values extraction.

### Core Modification Status
**No Core modifications were required.** All preview data is extracted from the existing public Core API.

### CLI Status
**CLI was untouched.** P6 is a UI-only feature.

---

## Frozen Architectural Decisions

1. **Technology Stack**: FastAPI + Pydantic v2 + Uvicorn HTTP server with initial server-rendered presentation, preserving a clean REST API seam for future SPA integration (ADR 001).
2. **Dependency Boundary**: `fbf-ui` depends directly on `fbf-core` (Tier 1 & Tier 2). No imports or subprocess calls to `fbf-cli` (ADR 002).
3. **File Handling & Path Security**: Explicit distinction between browser uploads, server filesystem references, persisted configs, and SQLite database paths. Server path references MUST resolve within configured `workspace_root` (ADR 003).
4. **Configuration Adapter**: `fbf-core`'s `StudyConfiguration` is the canonical source of truth, adapted via UI DTOs (ADR 004).
5. **Visualization Pipeline**: Financial metrics computed in Core; UI transforms execution results into visualization view models (ADR 005).

---

## Next Steps

1. Await explicit user commit authorization for Phase P6.
2. After P6 commit, update this file to reflect `COMPLETE`.
3. Request planning approval for **P7 — Non-Persistent Simulation Execution & Progress Engine**.

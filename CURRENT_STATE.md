# CURRENT_STATE.md — FBF UI Project State

## Repository State

| Property | Status |
|----------|--------|
| Package Version | `0.1.0` |
| Active Phase | `P11 — Historical Cohort Heatmap Visualization` |
| Phase State | `P11 COMPLETE — READY FOR COMMIT` |
| Core Dependency | `fbf-core 0.1.0` (editable sibling dependency) |
| Dedicated Venv | `/mnt/datos/workspace/fbf/fbf-ui/.venv` |
| Quality Gates | All passing (`ruff`, `mypy --strict`, `pytest`, boundary contracts, Playwright) |

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
- [x] **P8 — SQLite Database Browser & Persistence**: Read-only browser for persisted experiments, plans, and execution metadata via Core's `SQLiteRepository`.
- [x] **P9 — Persistent Simulation Logging**: Persist execution results to SQLite after completion.
- [x] **P10 — Result Summary Dashboard**: Results summary view with terminal wealth statistics, failure timeline, and portfolio trajectory charts.
- [x] **P11 — Historical Cohort Heatmap Visualization**: Parameter-first cohort × horizon heatmap with interactive parameter selector.

---

## Active Phase: P11 — Historical Cohort Heatmap Visualization

### Status
Implementation and all quality gates are **complete**. Working tree is ready for final pre-commit verification.
Awaiting explicit user authorization before creating the atomic commits for P11.

### Implemented in P11

**Core Repository (fbf-core):**
- `SQLiteRepository.get_available_parameters(result_id)` — Returns unique `(equity_allocation, withdrawal_rate)` selectors using SQL `json_extract()` on the `parameter_configurations` table. Does NOT use `params_hash` for partial selection.
- `SQLiteRepository.get_cohort_horizon_grid(result_id, equity_allocation, withdrawal_rate)` — Parameter-first filtered query that resolves matching `param_config_id`s via `json_extract()`, then reads only matching `simulation_results`. Returns cohort × horizon grid with success, failure_month, and terminal_wealth.
- 21 new Core repository tests covering all new methods plus ERN-scale benchmark gate.

**UI Orchestration (fbf-ui):**
- `PersistenceService.get_result_parameters()` → `AvailableParametersDTO`
- `PersistenceService.get_result_cohort_grid()` → `CohortGridDTO`
- DTOs: `ParameterSelectorDTO`, `AvailableParametersDTO`, `CohortGridDataDTO`, `CohortGridDTO`
- 15 new PersistenceService unit tests.

**UI API (fbf-ui):**
- `GET /api/v1/persistence/results/{result_id}/parameters` — Returns unique parameter selectors. 404 for missing result.
- `GET /api/v1/persistence/results/{result_id}/cohort-grid?equity_allocation=&withdrawal_rate=` — Returns cohort × horizon grid. 404 for missing result, 400 for missing/invalid parameters.
- 13 new API tests.

**UI Visualization (fbf-ui):**
- `ResultVisualizationTransformer.build_cohort_heatmap()` — Transforms `CohortGridDTO` into `ChartSpecDTO` with matrix chart type. Each cell contains `{"value": 1|0, "tooltip": "..."}`. Handles empty input deterministically.
- 29 new transformer tests.

**UI Frontend (fbf-ui):**
- Added cohort heatmap card to `results/detail.html` with parameter selector dropdown.
- `chartjs-chart-matrix@2.0.1` CDN dependency for heatmap rendering.
- JavaScript functions: `loadP11Parameters()`, `loadP11CohortGrid()`, `renderCohortHeatmap()`.
- Loading, empty, error, and success states.
- Responsive sizing with axis compression for large cohort counts.
- 12 new frontend unit tests.
- 24 new Playwright browser verification tests (all passing).

### Architecture (P11)

```
SQLiteRepository (fbf-core)
  ├── get_available_parameters()     — SQL json_extract on parameter_configurations
  ├── get_cohort_horizon_grid()      — parameter-first filtered query
  ↓
PersistenceService (fbf-ui)
  ├── get_result_parameters()  → AvailableParametersDTO
  ├── get_result_cohort_grid() → CohortGridDTO
  ↓
API Endpoints (fbf-ui)
  ├── GET /results/{id}/parameters
  ├── GET /results/{id}/cohort-grid?equity_allocation=&withdrawal_rate=
  ↓
ResultVisualizationTransformer (fbf-ui)
  ├── build_cohort_heatmap() → ChartSpecDTO (matrix)
  ↓
Frontend (results/detail.html)
  ├── chartjs-chart-matrix plugin
  ├── Parameter selector dropdown
  ├── renderCohortHeatmap(data)
  └── Canvas-based matrix rendering
```

### Key Design Decisions (P11)
- **Parameter-first resolution**: SQL `json_extract()` filters `parameter_configurations` (180 rows) before reading `simulation_results` (313K rows). 5.3× faster than full-scan approach.
- **No `params_hash` for partial selection**: The hash represents the complete config including `horizon_years`. Partial selection uses `json_extract()` subset match.
- **Unique selectors**: `/parameters` returns unique `(equity_allocation, withdrawal_rate)` pairs (45 for ERN), not 180 horizon-specific entries.
- **Binary heatmap**: Success (green) / failure (red) with tooltip showing cohort date, horizon, failure month, and terminal wealth.
- **No schema changes**: Leverages existing `params_json` structure and `json_extract` for filtering.

### Core APIs Consumed (P11)
- `get_available_parameters(result_id)` — Parameter selector listing.
- `get_cohort_horizon_grid(result_id, equity_allocation, withdrawal_rate)` — Filtered grid query.

### Core Modification Status (P11)
**Core was modified** with 2 new repository methods. All methods are backward-compatible additions. Existing methods unchanged.

---

## Frozen Architectural Decisions

1. **Technology Stack**: FastAPI + Pydantic v2 + Uvicorn HTTP server with initial server-rendered presentation, preserving a clean REST API seam for future SPA integration (ADR 001).
2. **Dependency Boundary**: `fbf-ui` depends directly on `fbf-core` (Tier 1 & Tier 2). No imports or subprocess calls to `fbf-cli` (ADR 002).
3. **File Handling & Path Security**: Explicit distinction between browser uploads, server filesystem references, persisted configs, and SQLite database paths. Server path references MUST resolve within configured `workspace_root` (ADR 003).
4. **Configuration Adapter**: `fbf-core`'s `StudyConfiguration` is the canonical source of truth, adapted via UI DTOs (ADR 004).
5. **Visualization Pipeline**: Financial metrics computed in Core; UI transforms execution results into visualization view models (ADR 005).

---

## Next Steps

1. Await explicit user commit authorization for Phase P11.
2. After P11 commit, update this file to reflect `COMPLETE`.
3. Proceed to **P12 — SWR & Capital Preservation Charts**.

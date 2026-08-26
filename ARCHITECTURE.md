# FBF UI Architecture — FIRE Backtesting Framework Web Interface

This document describes the high-level architecture of `fbf-ui`: the web interface, application orchestration layer, visualization pipeline, and API boundaries.

For architectural decision rationale, see [docs/DECISIONS.md](./docs/DECISIONS.md).

---

## 1. System Position & Boundaries

`fbf-ui` is a web delivery mechanism for the FIRE Backtesting Framework ecosystem. It is an independent peer to `fbf-cli`, depending directly on `fbf-core`:

```text
                 ┌─────────────────┐
                 │    fbf-core     │
                 │                 │
                 │ Simulation      │
                 │ Financial logic │
                 │ Research logic  │
                 │ Domain models   │
                 └────────▲────────┘
                          │
                     direct API
                          │
                 ┌────────┴────────┐
                 │     fbf-ui      │
                 │                 │
                 │ Application     │
                 │ Web/API         │
                 │ File workflows  │
                 │ Persistence     │
                 │ Visualization   │
                 └─────────────────┘

                 fbf-cli
                    ▲
                    │
                 independent
                 peer component
```

### Absolute Boundary Rules
1. **`fbf-ui` never imports `fbf-cli` or invokes CLI subprocesses.**
2. **`fbf-ui` never duplicates financial, simulation, allocation, or SWR optimization logic.**
3. **`fbf-core` never imports `fbf-ui`.**
4. **Presentation/API code never executes raw SQL.**

---

## 2. Layer Architecture

`fbf-ui` is organized into distinct architectural layers:

```text
┌─────────────────────────────────────────────────────────┐
│                    Presentation                         │
│   (Server-rendered HTML / Web Templates / Chart Specs)  │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP / DTOs
┌────────────────────────────▼────────────────────────────┐
│                      API Layer                          │
│             (FastAPI Routers & Endpoints)               │
└────────────────────────────┬────────────────────────────┘
                             │ DTOs / Service calls
┌────────────────────────────▼────────────────────────────┐
│             Application Orchestration Layer             │
│   (StudyService, ExecutionService, PersistenceService)  │
└──────────────┬───────────────────────────┬──────────────┘
               │                           │
┌──────────────▼──────────────┐ ┌──────────▼──────────────┐
│        fbf-core             │ │   Visualization Layer   │
│   (Study, Execution, SWR)   │ │  (View Models & Specs)  │
└──────────────┬──────────────┘ └─────────────────────────┘
               │
┌──────────────▼──────────────┐
│  fbf-core Persistence       │
│  (SQLiteRepository)         │
└─────────────────────────────┘
```

### 2.1 API Seam & Frontend Independence (ADR 001)
* FastAPI provides a strongly typed REST / HTTP API boundary.
* The API exposes decoupled DTOs (`Pydantic` schemas) rather than raw `fbf-core` domain objects.
* Initial delivery uses FastAPI + Jinja2 HTML templates and client-side Chart specs (Chart.js / Plotly.js).
* The API seam guarantees that a rich Single Page Application (SPA in React/Svelte/Vue) can be introduced seamlessly in future phases without modifying application or domain contracts.

### 2.2 Application Orchestration Services
* `StudyService`: Orchestrates YAML parsing (via `load_yaml`), configuration adaptation, and study plan validation (`build_study_plan`).
* `ExecutionService`: Coordinates dry runs, study plan execution (`execute_study_plan`), and SWR optimization (`optimize_study_swr`). Manages progress state machine:
  `IDLE` → `VALIDATING` → `READY` → `RUNNING` → (`COMPLETED` | `FAILED` | `CANCELLED`).
* `PersistenceService`: Manages SQLite repository interactions through `fbf.core.persistence` interfaces (`create_study_repository`).

### 2.3 Visualization Architecture (ADR 005)
Visualization logic is decoupled from simulation internals:
```text
fbf-core ResearchExecutionResult / SQLite DB
                     │
                     ▼
       UI Result/Query Adapter
                     │
                     ▼
        Visualization View Models
                     │
                     ▼
          Chart Specifications
                     │
                     ▼
           Frontend Renderer
```
Financial calculations are performed by Core. The UI visualization layer handles dataset aggregation, grouping, axis mapping, and chart view model construction.

---

## 3. Explicit File & Storage Semantics (ADR 003)

The architecture distinguishes 5 file handling modes:

1. **Uploaded Configuration**: User uploads a `.yaml` file via browser POST. Maintained in ephemeral session state or parsed directly into a DTO.
2. **Server Filesystem Reference**: Server reads an existing local configuration file path (e.g. `data/studies/example.yaml`) when running in local desktop mode.
3. **Browser Local Filesystem Reference**: Explicit handling of local file references via HTML5 File API / File System Access API where available.
4. **Persisted Configuration**: Study configuration serialized inside an SQLite experiment record.
5. **SQLite Database Reference**: Path to a local SQLite study database file (`.db` / `.sqlite`) managed by `fbf.core.persistence`.

---

## 4. Reproducibility Guarantee

Every simulation execution or result view model produced by `fbf-ui` records a complete **Reproducibility Envelope**:

```json
{
  "reproducibility": {
    "core_version": "0.1.0",
    "ui_version": "0.1.0",
    "study_configuration_hash": "a1b2c3...",
    "dataset_identifier": "sp500_historical",
    "execution_mode": "DECIMAL_FAST_PATH",
    "persistence_mode": "EPHEMERAL",
    "execution_timestamp": "2026-08-26T15:00:00Z"
  }
}
```

---

## 5. Architectural Contract Discipline

Layer boundaries are enforced automatically by `tests/contract/test_ui_boundaries.py`:
- `fbf.ui` must not import `fbf.cli`.
- `fbf.ui` must not execute CLI subprocesses.
- `fbf.ui` must not duplicate core financial/simulation arithmetic.
- Presentation code must not access SQLite directly.
- API endpoints must not contain business/simulation logic.
- `fbf-core` must not import `fbf.ui`.

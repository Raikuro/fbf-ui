# Architectural Decision Records (ADRs) — fbf-ui

This document records the architectural decision history for `fbf-ui`.

---

## ADR 001: Web Framework & Presentation Architecture

### Context
`fbf-ui` requires a high-performance, strongly typed web application delivery layer to expose `fbf-core` capabilities and render interactive financial charts.

### Decision
We select **FastAPI** + **Uvicorn** + **Pydantic v2** as the application backend framework, combined with server-rendered Jinja2 templates and client-side Chart specs (Chart.js / Plotly.js).

### Rationale
1. Native Python 3.13 support with 100% strict typing.
2. Fast async execution state polling for long-running backtests.
3. Explicit REST API seam (Pydantic DTOs) keeping frontend decoupled. If interactive complexity requires a full React/Svelte SPA in future phases, the API layer remains untouched.

### Rejected Alternatives
* *Streamlit / Gradio*: Rejected due to state mutation unpredictability, session isolation issues, and lack of explicit layer separation.
* *Heavy Node SPA (React/Vue) in Phase 1*: Deferred for initial bootstrap to keep single-command installation (`pip install -e .`) and agent productivity simple.

---

## ADR 002: Ecosystem Dependency Strategy & Independence

### Context
`fbf-ui` is part of the FBF ecosystem, which includes `fbf-core` (simulation engine) and `fbf-cli` (command line interface).

### Decision
`fbf-ui` depends directly on `fbf-core>=0.1.0,<0.2.0` (Tier 1 facade & Tier 2 modules). `fbf-ui` maintains zero dependency on `fbf-cli` and never invokes CLI subprocesses. `fbf-cli` and `fbf-ui` are parallel peer delivery mechanisms over `fbf-core`.

### Rationale
Clean architecture requires clear dependency direction. Web UI and CLI are presentation/delivery mechanisms. Neither should depend on the other.

---

## ADR 003: Explicit File & Storage Semantics & Path Security

### Context
Users need to load YAML study configurations and open SQLite study databases, operating across local desktop and web environments.

### Decision
`fbf-ui` explicitly categorizes 5 storage modes:
1. **Uploaded Configuration**: EPHEMERAL upload via HTTP multipart form (`POST /api/v1/study/upload`).
2. **Server Filesystem Reference**: Direct server path access (`POST /api/v1/study/parse-path`) constrained by a workspace security boundary. Server path references MUST resolve within a designated workspace root directory (`StudyService.workspace_root`). Arbitrary machine paths and path traversal attempts (`../`) escaping the workspace root are rejected with HTTP 403 Forbidden.
3. **Browser Local FS Reference**: HTML5 File API access.
4. **Persisted Configuration**: Inline configuration stored within SQLite experiment records.
5. **SQLite Database Reference**: Path to local `.db`/`.sqlite` file managed via `fbf.core.persistence`.

Arbitrary local path assumptions are forbidden in web-only browser modes.

---

## ADR 004: Canonical Configuration Model & UI DTO Boundary

### Context
`fbf-core` defines `StudyConfiguration` as the canonical domain representation for backtest parameters.

### Decision
`fbf-core`'s `StudyConfiguration` remains the single canonical source of truth for backtest configuration. `fbf-ui` exposes Pydantic DTOs (`StudyConfigDTO`) at the API layer, adapting to/from `StudyConfiguration` via `StudyService`.

### Rationale
Prevents duplicate financial configuration models while preventing presentation/API contracts from coupling directly to internal dataclasses.

---

## ADR 005: Visualization Pipeline Architecture

### Context
Financial visualizations (cohort heatmaps, SWR curves, glidepath comparisons) require data transformation before rendering.

### Decision
All financial calculations belong to `fbf-core`. `fbf-ui` provides a dedicated `visualization` transformation layer (`fbf.ui.visualization`) mapping `ResearchExecutionResult` or SQLite DB records to chart view models and JS chart specifications.

```text
fbf-core result / DB
        │
        ▼
UI Result Adapter
        │
        ▼
Visualization View Models
        │
        ▼
Chart Specification (JSON)
        │
        ▼
Client Renderer (Chart.js/Plotly.js)
```

Financial calculations MUST NOT be implemented inside JS chart code or presentation view templates.

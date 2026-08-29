# Phased Implementation Roadmap — fbf-ui

This document outlines the phased development roadmap for `fbf-ui`. Each phase is an independently reviewable delivery unit subject to quality gates and explicit commit authorization.

---

## Phase Breakdown

### P0 — Investigation & Architectural Seams (COMPLETE)
- Analyzed `fbf-core` and `fbf-cli` architecture, dependencies, conventions.
- Formulated technology decisions (FastAPI backend, Jinja2/Chart.js presentation, REST API DTO boundary).
- Produced capability matrix and visualization taxonomy.

### P1 — Project Bootstrap & Tooling (ACTIVE — READY FOR COMMIT)
- Initialized `fbf-ui` repository structure, packaging (`pyproject.toml`), setuptools.
- Established strict typing (`mypy --strict`), linting (`ruff`), and testing framework.
- Built FastAPI application shell with `/api/v1/health` endpoint returning actual installed `fbf-core` version.
- Implemented boundary contract tests (`tests/contract/test_ui_boundaries.py`).
- Created documentation infrastructure (`AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `CAPABILITY_MATRIX.md`, `VISUALIZATION_CATALOG.md`).

### P2 — Application Shell & UI Presentation Foundation
- Base Jinja2 HTML layout and navigation bar (Dashboard, Study, Run, Results, Compare, Persistence).
- Static assets pipeline and CSS styling.

### P3 — YAML Workflows & Configuration Parsing
- REST API `/api/v1/study/parse` endpoint integrating `fbf.core.study.builder.load_yaml`.
- File handling service: Uploaded YAML vs. Server filesystem path reference.

### P4 — Configuration Validation & DTO Mapping
- REST API `/api/v1/study/validate` endpoint.
- Validation error mapping and structured configuration DTO adapter.

### P5 — Structured Configuration Editor UI
- Form-based parameter editor with live validation feedback.
- Two-way synchronization between structured UI fields and canonical YAML.

### P6 — Dry Run Execution & Plan Preview
- REST API `/api/v1/study/preview` endpoint integrating `build_study_plan`.
- Preview panel displaying unit count, cohort grid, and execution parameter summary.

### P7 — Non-Persistent Simulation Execution & Progress Engine
- Execution state machine engine (`IDLE`, `RUNNING`, `COMPLETED`, `FAILED`).
- Async background simulation runner calling `execute_study_plan`.
- Real-time progress polling endpoint.

### P8 — SQLite Database Browser (COMPLETE)
- Read-only browser for persisted experiments, plans, and execution metadata.
- Core repository methods: `list_experiments_with_plans()`, `list_plans_for_experiment()`, `get_experiment_metadata()`, `get_execution_result_metadata()`.
- API endpoints: `/api/v1/persistence/experiments`, `/api/v1/persistence/experiments/{id}`, `/api/v1/persistence/experiments/{id}/plans`, `/api/v1/persistence/plans/{id}/results`.
- Presentation: Experiment list browser and experiment detail page.

### P9 — Persistent Simulation Logging
- Simulation runner executing studies directly into local SQLite database files.

### P10 — Non-Persistent Result Summary Dashboard
- Results summary view (success rate, terminal wealth statistics, worst-case cohorts).

### P11 — Historical Cohort Heatmap Visualizations
- View model transformer & Chart spec generator for Cohort heatmaps.

### P12 — Safe Withdrawal Rate (SWR) & Capital Preservation Charts
- SWR curve generator calling `optimize_study_swr` and rendering interactive SWR curves.

### P13 — Multi-Strategy Comparator
- Side-by-side strategy comparator for multiple persisted database experiments.

### P14 — Result Exporter & Reproducibility Package
- Export study results & charts to CSV, JSON, and YAML packages with full Reproducibility Envelopes.

### P15 — Hardening & E2E Validation
- High-value end-to-end integration tests (Import YAML -> Run -> View Results).

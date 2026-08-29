# TODO.md — Canonical Technical Register for fbf-ui

This document records verified, open technical work in `fbf-ui`.

---

## Completed Tasks

- [x] **P1 Bootstrap**: Standalone repository packaging, strict mypy/ruff/pytest quality gates, dedicated `.venv`, boundary contract tests, architecture docs.
- [x] **P2 Application Shell & Presentation Foundation**: Jinja2 base templates, static dark theme CSS, 6 scaffolded routes with active tab navigation, package-relative path resolution, presentation route unit tests.
- [x] **P3 YAML Import & File Workflows**: `/api/v1/study/upload`, `/api/v1/study/parse-path`, `/api/v1/study/parse-text` endpoints; `StudyConfigDTO`; workspace path security boundary; 11 HTTP contract tests; ADR 003 updated.
- [x] **P4 Execution State Engine**: Background execution task manager with progress status endpoints, cancellation semantics, and ThreadPoolExecutor orchestration.
- [x] **P5 Structured Configuration Editing**: Editable form for parsed `StudyConfigDTO` fields; mutation and re-validation workflow.
- [x] **P6 Study Plan Dry Run & Preview**: `BuiltStudy` plan summary (cohort count, date ranges) before committing to full execution.
- [x] **P7 Simulation Execution**: Connected configuration/preview workflow to Core execution engine via DTO-based endpoint, Execute button in editor, progress polling, and result storage.
- [x] **P8 SQLite Database Browser & Persistence**: Read-only browser for persisted experiments, plans, and execution metadata via Core's `SQLiteRepository`.

---

## Upcoming Technical Tasks

- [ ] **P9 Persistent Simulation Logging**: Persist P7 in-memory execution results to SQLite after completion.
- [ ] **P10 Non-Persistent Result Summary Dashboard**: Results summary view (success rate, terminal wealth statistics, worst-case cohorts).
- [ ] **P11 Historical Cohort Heatmap Visualizations**: View model transformer & Chart spec generator for Cohort heatmaps.
- [ ] **P12 SWR & Capital Preservation Charts**: SWR curve generator calling `optimize_study_swr` and rendering interactive SWR curves.
- [ ] **P13 Multi-Strategy Comparator**: Side-by-side strategy comparator for multiple persisted database experiments.
- [ ] **P14 Result Exporter & Reproducibility Package**: Export study results & charts to CSV, JSON, and YAML packages.
- [ ] **P15 Hardening & E2E Validation**: High-value end-to-end integration tests.

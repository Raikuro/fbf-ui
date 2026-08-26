# TODO.md — Canonical Technical Register for fbf-ui

This document records verified, open technical work in `fbf-ui`.

---

## Completed Tasks

- [x] **P1 Bootstrap**: Standalone repository packaging, strict mypy/ruff/pytest quality gates, dedicated `.venv`, boundary contract tests, architecture docs.
- [x] **P2 Application Shell & Presentation Foundation**: Jinja2 base templates, static dark theme CSS, 6 scaffolded routes with active tab navigation, package-relative path resolution, presentation route unit tests.
- [x] **P3 YAML Import & File Workflows**: `/api/v1/study/upload`, `/api/v1/study/parse-path`, `/api/v1/study/parse-text` endpoints; `StudyConfigDTO`; workspace path security boundary; 11 HTTP contract tests; ADR 003 updated.

---

## Upcoming Technical Tasks

- [ ] **P4 Execution State Engine**: Implement background execution task manager for non-blocking simulation runs with progress status endpoints.
- [ ] **P5 Structured Configuration Editing**: Implement editable form for parsed `StudyConfigDTO` fields; mutation and re-validation workflow.
- [ ] **P6 Study Plan Dry Run & Preview**: Display `BuiltStudy` plan summary (cohort count, date ranges) before committing to full execution.
- [ ] **P7 Simulation Backtest Execution**: Wire `execute_study_plan` into execution service, display running state and final completion.
- [ ] **P8/P9 SQLite Database Browser & Persistence**: Implement `/api/v1/persistence/studies` to query historical studies via Core's `SQLiteRepository`.

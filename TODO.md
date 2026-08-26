# TODO.md — Canonical Technical Register for fbf-ui

This document records verified, open technical work in `fbf-ui`.

---

## Completed Tasks

- [x] **P1 Bootstrap**: Standalone repository packaging, strict mypy/ruff/pytest quality gates, dedicated `.venv`, boundary contract tests, architecture docs.
- [x] **P2 Application Shell & Presentation Foundation**: Jinja2 base templates, static dark theme CSS, 6 scaffolded routes with active tab navigation, package-relative path resolution, presentation route unit tests.

---

## Upcoming Technical Tasks

- [ ] **P3 YAML Workflow Service**: Implement `/api/v1/study/parse` endpoint to accept uploaded YAML content or server path references via `StudyService`.
- [ ] **P4 Execution State Engine**: Implement background execution task manager for non-blocking simulation runs with progress status endpoints.
- [ ] **P5 SQLite Database Browser**: Implement `/api/v1/persistence/studies` endpoint to query historical studies from local `.db`/`.sqlite` files via Core's `SQLiteRepository`.

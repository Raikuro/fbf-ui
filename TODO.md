# TODO.md — Canonical Technical Register for fbf-ui

This document records verified, open technical work in `fbf-ui`.

---

## Technical Tasks

- [ ] **P2 Application Navigation Layout**: Implement base HTML layout template with nav header (Dashboard, Study, Run, Results, Compare, Persistence).
- [ ] **P3 YAML Workflow Service**: Implement `/api/v1/study/parse` endpoint to accept uploaded YAML content or server path references via `StudyService`.
- [ ] **P4 Execution State Engine**: Implement background execution task manager for non-blocking simulation runs with progress status endpoints.
- [ ] **P5 SQLite Database Browser**: Implement `/api/v1/persistence/studies` endpoint to query historical studies from local `.db`/`.sqlite` files via Core's `SQLiteRepository`.

# CURRENT_STATE.md — FBF UI Project State

## Repository State

| Property | Status |
|----------|--------|
| Package Version | `0.1.0` |
| Active Phase | `P3 — YAML Import & File Workflows` |
| Phase State | `PHASE P3 READY FOR COMMIT — AWAITING AUTHORIZATION` |
| Core Dependency | `fbf-core 0.1.0` (editable sibling dependency) |
| Dedicated Venv | `/mnt/datos/workspace/fbf/fbf-ui/.venv` |
| Quality Gates | All passing (`ruff`, `mypy --strict`, `pytest`, boundary contracts) |

---

## Completed Milestones & Phases

- [x] **P0 — Repository Architecture & Investigation**: Evaluated stack options, established dependency strategy, defined layer boundaries, produced capability matrix and visualization catalog.
- [x] **P1 — Project Bootstrap & Tooling** (Frozen at commit `5009989`): Created `fbf-ui` package, set up setuptools configuration, dedicated `.venv`, FastAPI app shell, health endpoint reporting installed `fbf-core` version, contract tests, and documentation.
- [x] **P2 — Application Shell & UI Presentation Foundation** (Frozen at commit `5d7cd2c`): Built Jinja2 presentation templates (`base.html`, `dashboard.html`, `study.html`, `run.html`, `results.html`, `compare.html`, `persistence.html`), static dark theme CSS (`/static/css/app.css`), package-relative path resolution, active tab navbar highlighting, template unit tests, and scaffolding placeholders.

---

## Active Phase: P3 — YAML Import & File Workflows

### Status
Implementation and quality gate validation are **complete**. Working tree is ready for final pre-commit verification.
Awaiting explicit user authorization before creating the single atomic commit for Phase P3.

### Implemented in P3
- `src/fbf/ui/api/study.py` — `POST /api/v1/study/upload`, `POST /api/v1/study/parse-path`, `POST /api/v1/study/parse-text` endpoints.
- `src/fbf/ui/orchestration/study_service.py` — `StudyConfigDTO`, `StudyService.parse_yaml_text()`, `StudyService.parse_server_file()`, `StudyService.resolve_permitted_path()`, workspace path security boundary.
- `src/fbf/ui/api/router.py` — Includes `study_router` under `/api/v1`.
- `src/fbf/ui/presentation/templates/study.html` — File upload, server path, raw text, and display sections.
- `tests/unit/test_study_api.py` — 11 HTTP contract tests covering all success and failure paths.
- `tests/contract/test_ui_boundaries.py` — New `test_api_does_not_access_sqlite` contract test (6 total).
- `pyproject.toml` — Added `python-multipart>=0.0.9` runtime dependency.
- `ARCHITECTURE.md`, `docs/DECISIONS.md` — ADR 003 updated with workspace path security boundary.

---

## Frozen Architectural Decisions

1. **Technology Stack**: FastAPI + Pydantic v2 + Uvicorn HTTP server with initial server-rendered presentation, preserving a clean REST API seam for future SPA integration (ADR 001).
2. **Dependency Boundary**: `fbf-ui` depends directly on `fbf-core` (Tier 1 & Tier 2). No imports or subprocess calls to `fbf-cli` (ADR 002).
3. **File Handling & Path Security**: Explicit distinction between browser uploads, server filesystem references, persisted configs, and SQLite database paths. Server path references MUST resolve within configured `workspace_root` (ADR 003).
4. **Configuration Adapter**: `fbf-core`'s `StudyConfiguration` is the canonical source of truth, adapted via UI DTOs (ADR 004).
5. **Visualization Pipeline**: Financial metrics computed in Core; UI transforms execution results into visualization view models (ADR 005).

---

## Next Steps

1. Await explicit user commit authorization for Phase P3.
2. After P3 commit, update this file to reflect `COMPLETE`.
3. Request planning approval for **P4 — Execution State Engine**.

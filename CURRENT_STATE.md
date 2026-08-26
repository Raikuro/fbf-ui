# CURRENT_STATE.md — FBF UI Project State

## Repository State

| Property | Status |
|----------|--------|
| Package Version | `0.1.0` |
| Active Phase | `P1 — Bootstrap and Tooling` |
| Phase State | `PHASE P1 READY FOR COMMIT — AWAITING AUTHORIZATION` |
| Core Dependency | `fbf-core 0.1.0` (editable sibling dependency) |
| Quality Gates | All passing (`ruff`, `mypy --strict`, `pytest`, boundary contracts) |

---

## Completed Milestones & Phases

- [x] **P0 — Repository Architecture & Investigation**: Evaluated stack options, established dependency strategy, defined layer boundaries, produced capability matrix and visualization catalog.
- [x] **P1 — Project Bootstrap & Tooling**: Created `fbf-ui` package, set up setuptools configuration, FastAPI app shell, health endpoint reporting installed `fbf-core` version, contract tests, and documentation.

---

## Active Phase: P1 Bootstrap

### Status
Implementation and quality gate validation are **complete**. Working tree is ready.
Awaiting explicit user authorization before creating the single atomic commit for Phase P1.

---

## Frozen Architectural Decisions

1. **Technology Stack**: FastAPI + Pydantic v2 + Uvicorn HTTP server with initial server-rendered presentation, preserving a clean REST API seam for future SPA integration (ADR 001).
2. **Dependency Boundary**: `fbf-ui` depends directly on `fbf-core` (Tier 1 & Tier 2). No imports or subprocess calls to `fbf-cli` (ADR 002).
3. **File Handling**: Explicit distinction between browser uploads, server filesystem references, persisted configs, and SQLite database paths (ADR 003).
4. **Configuration Adapter**: `fbf-core`'s `StudyConfiguration` is the canonical source of truth, adapted via UI DTOs (ADR 004).
5. **Visualization Pipeline**: Financial metrics computed in Core; UI transforms execution results into visualization view models (ADR 005).

---

## Next Steps

1. Request user authorization for Phase P1 commit.
2. After commit creation, update Phase P1 to `COMPLETE`.
3. Proceed to **P2 — Application Shell & Navigation Layout**.

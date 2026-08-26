# AGENTS.md — fbf-ui Agent Guide

This is the standalone `fbf-ui` repository.
It contains the web application interface, application orchestration services, API routes, presentation layer, and interactive visualization engine for the FIRE Backtesting Framework.

---

## Repository Identity

| Property | Value |
|----------|-------|
| Package name | `fbf-ui` |
| Root namespace | `fbf.ui` |
| Runtime dependencies | `fbf-core>=0.1.0,<0.2.0`, `pyyaml>=6.0`, `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `pydantic>=2.6.0`, `jinja2>=3.1.0` |
| Python requirement | ≥ 3.13 |
| Console entry point | `fbf-ui` |

---

## Absolute Rules

1. **Never import `fbf.cli` or invoke CLI subprocesses.** `fbf-ui` is a parallel peer delivery component to `fbf-cli`. It interacts exclusively with `fbf-core`.
2. **Never import Core Tier 3 internals.** UI production code may only import Core via Tier 1 facade (`fbf.core`) or documented Tier 2 modules (`fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence`, `fbf.core.domain`).
3. **Never duplicate financial or simulation logic.** All financial arithmetic, SWR solving, portfolio calculations, and policy execution belong strictly in `fbf-core`.
4. **Presentation/API code must never execute raw SQL.** Direct SQL execution in presentation or web router code is forbidden. Database interactions MUST pass through `fbf.core.persistence` repository interfaces.
5. **fbf-core Modification Gate:** The agent must **immediately stop and request explicit user authorization** if completing a UI task requires modifying any code, API, dependency, or configuration in `fbf-core`. Never introduce a UI workaround to bypass a missing core capability.
6. **No machine-specific absolute paths** (`/tmp/`, `/home/`, `/Users/`, `C:\`) in `src/` or `tests/`.
7. **Core must not import UI.** Never reference `fbf.ui` inside `fbf-core`.

---

## Quality Gate

Run every command below from a clean checkout **before** committing to `fbf-ui`.
A change that does not pass every step is not committed.

```bash
# 1. Lint — must report "All checks passed!"
ruff check src tests

# 2. Type check — must report "Success: no issues found in N source files"
mypy --strict src

# 3. Full test suite — must be 0 failed
pytest -p no:cacheprovider

# 4. Boundary contract — boundary discipline + no CLI imports
pytest tests/contract/
```

---

## Commit Governance

### Phase completion vs. commit authorization

A phase is **not complete until its final commit has been created successfully**.
However, completing implementation work does **not** give implicit permission to commit.

The required workflow is:

1. Implement the approved scope.
2. Run all required validation and quality gates.
3. Review final diff and confirm approved phase scope.
4. Prepare repository for the final phase commit.
5. **Stop and request explicit user authorization to create the commit.**
6. Do not run `git commit` before explicit authorization is given.
7. After authorization, create **exactly one commit for the phase**.
8. Verify commit hash and clean working tree.
9. Report phase as `COMPLETE`.

Report state before authorization as:
> `PHASE X READY FOR COMMIT — AWAITING AUTHORIZATION`

### One-commit-per-phase rule

Each phase is an atomic delivery unit and must produce **exactly one final commit**.

---

## Documentation Authority

| Question | Authority |
|----------|-----------|
| Current code behavior | Code + tests |
| Intended UI architecture | ARCHITECTURE.md |
| Rejected architectural alternatives | docs/DECISIONS.md |
| CLI to UI capability map | docs/CAPABILITY_MATRIX.md |
| Visualization catalog | docs/VISUALIZATION_CATALOG.md |
| Phased roadmap | docs/ROADMAP.md |
| Current project state | CURRENT_STATE.md |
| Technical TODOs | TODO.md |

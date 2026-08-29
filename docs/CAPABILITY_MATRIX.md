# CLI-to-UI Capability Traceability Matrix — fbf-ui

This document maps all capabilities exposed by `fbf-cli` to their corresponding `fbf-core` APIs and planned `fbf-ui` features.

---

## Traceability Mapping

| CLI Command | Core / Application Capability | Planned UI Feature / Route | Phase |
|-------------|-------------------------------|----------------------------|-------|
| `fbf validate <yaml>` | `load_yaml`, `build_study_plan` | Study Validation Panel & `/api/v1/study/validate` | P4 |
| `fbf config show/template` | `StudyConfiguration.default()` | Config Generator & Structured Editor (`/study/edit`) | P5 |
| `fbf run --dry-run` | `build_study_plan` (materials & stats) | Dry Run Execution Preview (`/run/preview`) | P6 |
| `fbf run <yaml>` | `execute_study_plan` | Non-Persistent Simulation Dashboard (`/run/execute`) | P7 |
| `fbf run --db <db>` | `create_study_repository`, `execute_study_plan` | Persistent Simulation & Experiment Logging (`/run/persistent`) | P9 |
| `fbf optimize` | `optimize_study_swr` | Interactive SWR Optimizer Interface (`/optimize`) | P12 |
| `fbf list --db <db>` | `SQLiteRepository.list_experiments_with_plans()` | Database Experiment Browser (`/persistence`) | P8 |
| `fbf compare <ids>` | Database experiment query & cross-study metric comparison | Visual Strategy & Experiment Comparator (`/compare`) | P13 |
| `fbf export` | `ResearchExecutionResult` serialization | Multi-format Result Exporter (CSV, JSON, YAML) | P14 |

---

## Execution & Storage Semantics Matrix

| Workflow | Inputs | Execution Engine | Storage Target | UI Surface |
|----------|--------|------------------|----------------|------------|
| **Interactive Research** | Uploaded YAML / Web Form | `execute_study_plan` (Decimal Fast Path) | Ephemeral Session | Results Dashboard |
| **Persistent Study** | Server YAML / DB experiment | `execute_study_plan` + `SQLiteRepository` | SQLite `.db` file | Persistence Workspace |
| **SWR Grid Search** | Parameter sweeps | `optimize_study_swr` | DB or Ephemeral | SWR Curve & Heatmaps |

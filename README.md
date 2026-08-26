# FBF UI — FIRE Backtesting Framework Web Interface

`fbf-ui` is the web-based user interface, application orchestration server, and interactive visualization engine for the **FIRE Backtesting Framework (FBF)**.

It provides a graphical web interface to configure studies, validate parameters, run dry runs and simulations, optimize Safe Withdrawal Rates (SWR), browse persisted study databases, and explore interactive financial charts.

---

## Ecosystem Architecture

`fbf-ui` is a standalone repository within the FBF ecosystem, positioned alongside `fbf-core` and `fbf-cli`:

```text
parent/
├── fbf-core/    # Simulation engine & research library (stdlib only)
├── fbf-cli/    # Terminal command-line delivery mechanism
└── fbf-ui/     # Web interface, orchestration & visualization
```

`fbf-ui` depends directly on `fbf-core`. It does **not** depend on `fbf-cli` or invoke CLI subprocesses.

---

## Features

- **FastAPI Orchestration Backend**: Typed REST API endpoints with health reporting and execution state tracking.
- **Canonical Configuration Editing**: Seamless YAML loading, validation, and structured configuration DTO mapping via `fbf-core`.
- **Visualization Catalog**: Decoupled view-model transformation pipeline for historical cohort heatmaps, SWR sensitivity, capital preservation distributions, glidepath comparisons, and strategy analysis.
- **Persistence Integration**: Seamless browsing and historical analysis of SQLite study databases created by `fbf-core` or `fbf-cli`.
- **Reproducibility Tracking**: Automated tracking of configuration hashes, dataset versions, engine versions, and execution parameters.

---

## Development Setup

### 1. Prerequisites
- Python ≥ 3.13
- Sibling checkout of `fbf-core`

### 2. Environment Installation

```bash
# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# Install fbf-core in editable mode first, followed by fbf-ui with dev dependencies
pip install -e ../fbf-core -e .[dev]
```

### 3. Quality Gate Commands

Run all quality checks before requesting commit authorization:

```bash
# 1. Linting
ruff check src tests

# 2. Strict Type Checking
mypy --strict src

# 3. Test Suite
pytest -p no:cacheprovider

# 4. Boundary Contracts
pytest tests/contract/
```

### 4. Running the Web Server

```bash
# Run via console entry point
fbf-ui

# Or run via uvicorn directly
uvicorn fbf.ui.main:app --reload --port 8000
```

Health check endpoint: `http://localhost:8000/api/v1/health`

---

## License

MIT License. See [LICENSE](LICENSE) for details.

# P11 — Architectural Design Report (Revised v2)

## A. Current Architecture

### Data Path (P8 → P10)

```
SQLite (simulation_results, planned_units, cohorts, parameter_configurations)
  ↓
fbf-core SQLiteRepository
  ├── get_result_statistics()      — reads final_month=1 rows, aggregates across all units
  ├── get_result_trajectory_percentiles() — reads ALL monthly rows, computes percentile bands
  └── get_export_data()            — joins planned_units→cohorts→params, returns flat rows
  ↓
PersistenceService
  ├── get_result_summary_by_id()   → ResultSummaryDTO
  ├── get_result_statistics()      → ResultStatisticsDTO
  └── get_result_trajectory()      → TrajectoryDTO
  ↓
API Endpoints (GET /results/{id}/summary|statistics|trajectory)
  ↓
ResultVisualizationTransformer
  ├── build_wealth_distribution_chart()   → ChartSpecDTO (bar)
  ├── build_failure_timeline_chart()      → ChartSpecDTO (bar)
  ├── build_trajectory_chart()            → ChartSpecDTO (line)
  ├── build_summary_card()                → SummaryCardDTO
  ├── build_empty_cohort_chart()          → ChartSpecDTO (heatmap) ← placeholder
  └── build_swr_curve_chart()             → ChartSpecDTO (line)
  ↓
Chart.js 4.4.7 (CDN) in results/detail.html
```

### Key Schema Tables for P11

| Table | Relevant Columns | Join Path |
|-------|-----------------|-----------|
| `simulation_results` | `execution_result_id`, `unit_index`, `final_month`, `statistics_payload_json` | → `execution_results` via FK |
| `execution_results` | `result_id`, `plan_id` | → `research_plans` via FK |
| `research_plans` | `plan_id`, `experiment_id` | → `experiments` via FK |
| `planned_units` | `plan_id`, `unit_index`, `cohort_id`, `param_config_id` | → `cohorts`, `parameter_configurations` |
| `cohorts` | `cohort_id`, `experiment_id`, `start_date` | canonical cohort identity |
| `parameter_configurations` | `param_config_id`, `params_json`, `params_hash` | contains `horizon_years`, `equity_allocation`, `withdrawal_rate` |

### Existing Cohort-Aware Query

Only `get_export_data()` joins `planned_units` → `cohorts` → `parameter_configurations`. It is the proven join pattern. It reads ALL monthly rows (O(units × months)) which is expensive for large grids.

### Existing `statistics_payload_json` Structure

```json
{
  "final_wealth_amount": "123456.78",
  "final_wealth_currency": "EUR",
  "max_drawdown": 0.0,
  "success": true,
  "failure_month": null,
  "months_simulated": 361,
  "execution_time_seconds": 0.0
}
```

Stored only on `final_month = 1` rows. One row per unit.

### Existing `params_json` Structure

```json
{
  "equity_allocation": 0.5,
  "withdrawal_rate": 0.04,
  "horizon_years": 30
}
```

### Canonical JSON Serialization

`params_json` is serialized with `json.dumps(data, sort_keys=True, separators=(',', ':'))`. Keys are sorted alphabetically, compact separators. The `params_hash` is `sha256(params_json)`. Both are fully deterministic from the parameter values — no database lookup needed to compute them.

**`params_hash` identity**: Each `params_hash` represents a complete parameter configuration including `horizon_years`. The hash of `(equity=0.5, withdrawal=0.04, horizon=30)` is different from the hash of `(equity=0.5, withdrawal=0.04, horizon=40)`. The `params_hash` can be used to resolve an exact configuration, but **cannot** be used for partial parameter selection (e.g., selecting all horizons for a given equity/withdrawal pair).

---

## B. P11 Data Requirements

The cohort × horizon heatmap requires, for each simulation unit:

| Field | Source | Persisted? |
|-------|--------|-----------|
| Cohort start date | `cohorts.start_date` | Yes |
| Horizon years | `parameter_configurations.params_json → "horizon_years"` | Yes |
| Equity allocation | `parameter_configurations.params_json → "equity_allocation"` | Yes |
| Withdrawal rate | `parameter_configurations.params_json → "withdrawal_rate"` | Yes |
| Success | `statistics_payload_json → "success"` | Yes (final_month=1) |
| Failure month | `statistics_payload_json → "failure_month"` | Yes (final_month=1) |
| Terminal wealth | `statistics_payload_json → "final_wealth_amount"` | Yes (final_month=1) |

**All required data is already persisted. No schema changes needed.**

---

## C. Data Availability

### Where the fields live

- **Cohort identity**: `cohorts.start_date` (TEXT, ISO format). Joined via `planned_units.cohort_id → cohorts.cohort_id`.
- **Horizon**: Inside `parameter_configurations.params_json` as `"horizon_years"` key. Joined via `planned_units.param_config_id → parameter_configurations.param_config_id`.
- **Statistics**: Inside `simulation_results.statistics_payload_json` on `final_month = 1` rows.

### Critical Architectural Insight: Parameter-First Resolution

The original design proposed reading ALL simulation results and filtering by parameters in Python. This is wasteful: for a single parameter selection, it processes 180× more rows than necessary.

**Revised approach**: Resolve the parameter configuration BEFORE reading simulation results.

```
1. Filter parameter_configurations by (equity_allocation, withdrawal_rate)
   — scans 180 rows (tiny), returns matching param_config_ids
         ↓
2. SELECT unit_index FROM planned_units
   WHERE plan_id = ? AND param_config_id IN (matching_ids)
   — uses idx_units_plan, returns ~6,956 unit_indices (for ERN)
         ↓
3. SELECT statistics_payload_json FROM simulation_results
   WHERE execution_result_id = ? AND final_month = 1
     AND unit_index IN (...)
   — uses PK index, reads exactly ~6,956 rows
         ↓
4. Parse statistics JSON → build cohort × horizon grid
```

**Key property**: `simulation_results` is filtered in SQL BEFORE Python processing. The parameter resolution step scans only the tiny `parameter_configurations` table (180 rows), which is negligible compared with 313K simulation rows.

**Cost comparison (ERN full grid, single parameter set)**:

| Approach | parameter_configurations scan | simulation_results rows read | Python JSON parses | Total |
|----------|-------------------------------|------------------------------|-------------------|-------|
| Full-scan (original) | N/A | 313,020 | 626,040 (params + stats) | O(all units) |
| Parameter-first (revised) | 180 rows | 6,956 | 6,956 (stats only) | O(matching units) |

The parameter-first approach reads **45× fewer simulation rows** and performs **90× fewer Python JSON deserializations** for a single parameter selection. The 180-row parameter scan is irrelevant in comparison.

### JSON Deserialization Breakdown

The benchmark measured 626,040 JSON deserializations for the full-scan approach. This is because the full scan deserializes **two** JSON payloads per row in Python:

- 313,020 `params_json` parses (to check equity_allocation and withdrawal_rate)
- 313,020 `statistics_payload_json` parses (to extract success/failure data)
- Total: 626,040 Python `json.loads()` calls

The parameter-first approach avoids `params_json` Python deserialization entirely — SQL `json_extract()` handles parameter filtering at the database level. Only the 6,956 matching `statistics_payload_json` payloads are parsed in Python.

---

## D. Research Semantics

### What each cell represents

For a fixed parameter set `(equity_allocation=W, withdrawal_rate=R)`:

```
cell(cohort_start_date, horizon_years) = {
    success: bool,
    failure_month: int | null,
    terminal_wealth: float
}
```

**Primary metric**: `success` (boolean) — did the portfolio survive the full horizon?

**Secondary metrics** (tooltip detail):
- `failure_month`: When failure occurred (month index), if applicable
- `terminal_wealth`: Final portfolio value

### What each heatmap shows

The heatmap displays a **2D matrix** where:

- **Y-axis** (rows): Cohort start dates, ordered chronologically (earliest at bottom)
- **X-axis** (columns): Retirement horizon values (e.g., 30, 40, 50, 60 years)
- **Cell color**: Green = success, Red = failure (binary)
- **Tooltip**: Cohort date, horizon, terminal wealth, failure month

### Why this is meaningful

This visualization directly answers the core FIRE research question:

> "If I had retired in month X with horizon Y, would my money have lasted?"

The green/red pattern reveals:
- **Sequence-of-returns risk structure**: Which historical periods are dangerous
- **Horizon sensitivity**: How extending retirement horizon affects survival
- **Cohort clustering**: Whether failures cluster in specific historical periods
- **Safety zones**: Which cohorts are consistently safe across horizons

### Aggregation semantics

For a single parameter set, each cell maps to exactly **one** simulation unit (1 cohort × 1 horizon × 1 parameter set). No aggregation is needed — each cell is a direct simulation result.

If the user requests a view that aggregates across parameter sets (e.g., "success rate across all withdrawal rates for each cohort × horizon"), that is a separate, more complex visualization. P11 will not implement this — it shows one parameter set at a time.

---

## E. Query Design

### Two Core Repository Methods

#### Method 1: `get_available_parameters(result_id)`

Returns unique parameter selectors for a result. Used to populate the parameter selector dropdown.

The selector is `(equity_allocation, withdrawal_rate)`. The grid endpoint accepts this selector and returns **all horizons** for the matching configurations.

```python
def get_available_parameters(self, result_id: str) -> list[dict[str, Any]] | None:
    """Return unique parameter selectors for an execution result.

    Returns None when the result_id does not exist.
    Returns a list of dicts, each with:
        - equity_allocation: float
        - withdrawal_rate: float
    Ordered by equity_allocation, withdrawal_rate.
    """
```

**SQL:**

```sql
SELECT DISTINCT
    json_extract(pc.params_json, '$.equity_allocation') AS equity_allocation,
    json_extract(pc.params_json, '$.withdrawal_rate')  AS withdrawal_rate
FROM planned_units pu
JOIN parameter_configurations pc ON pu.param_config_id = pc.param_config_id
JOIN execution_results er ON er.plan_id = pu.plan_id
WHERE er.result_id = ?
ORDER BY equity_allocation, withdrawal_rate;
```

**Returns** (for ERN full grid): 45 rows (5 equity × 9 withdrawal rates). ~1KB payload.

#### Method 2: `get_cohort_horizon_grid(result_id, equity_allocation, withdrawal_rate)`

Returns the cohort × horizon grid for a specific parameter selector.

```python
def get_cohort_horizon_grid(
    self,
    result_id: str,
    equity_allocation: float,
    withdrawal_rate: float,
) -> dict | None:
    """Return the cohort × horizon success/failure grid for a parameter set.

    Returns None when:
      - result_id does not exist
      - No units match the parameter filter

    Parameter resolution: filters parameter_configurations by json_extract
    to find matching param_config_ids, then reads only matching simulation results.
    """
```

**SQL:**

```sql
SELECT
    c.start_date AS cohort_start_date,
    json_extract(pc.params_json, '$.horizon_years') AS horizon_years,
    sr.statistics_payload_json
FROM simulation_results sr
JOIN execution_results er ON sr.execution_result_id = er.result_id
JOIN planned_units pu ON pu.plan_id = er.plan_id AND pu.unit_index = sr.unit_index
JOIN cohorts c ON pu.cohort_id = c.cohort_id
JOIN parameter_configurations pc ON pu.param_config_id = pc.param_config_id
WHERE sr.execution_result_id = ?
  AND sr.final_month = 1
  AND json_extract(pc.params_json, '$.equity_allocation') = ?
  AND json_extract(pc.params_json, '$.withdrawal_rate') = ?
ORDER BY c.start_date, horizon_years;
```

**Alternative (two-step)**: Resolve matching `param_config_id`s first, then filter `planned_units` by those IDs. Both approaches achieve the same property: simulation data is filtered in SQL before Python processing.

### Python Post-Processing

For each row returned by the query:
1. Parse `statistics_payload_json` → extract `success`, `failure_month`, `final_wealth_amount`
2. Group by `(cohort_start_date, horizon_years)`
3. Build grid arrays aligned with sorted cohort list and sorted horizon list

### Return Structure

```python
{
    "result_id": str,
    "cohorts": list[str],           # sorted unique cohort start dates
    "horizons": list[int],          # sorted unique horizon years (derived from matching configs)
    "parameters": {
        "equity_allocation": float,
        "withdrawal_rate": float,
    },
    "grid": {
        "success": list[list[bool]],           # [cohort_idx][horizon_idx]
        "failure_month": list[list[int | None]],
        "terminal_wealth": list[list[float]],
    },
    "total_units": int,             # units matching the filter
    "success_count": int,
    "failure_count": int,
}
```

### Complexity

- **Parameter configuration scan**: O(180) — negligible (parameter_configurations table is tiny)
- **Rows read from simulation_results**: O(units_matching_params) — ~6,956 for ERN (not 313K)
- **Python JSON parses**: O(units_matching_params) — ~6,956 (not 626K)
- **Python grouping**: O(units_matching_params)
- **Output size**: O(cohorts × horizons) — 1,739 × 4 = 6,956 cells

---

## F. Cost Model

### ERN Full Grid Reference (ern_grid.yaml)

| Metric | Value |
|--------|-------|
| Cohorts | 1,739 |
| Parameter configs | 180 |
| Unique selectors (equity, withdrawal) | 45 |
| Total units | 313,020 |
| Horizons | 4 (30, 40, 50, 60 years) |
| final_month=1 rows | 313,020 |
| Units per selector | ~6,956 (1,739 cohorts × 4 horizons) |

### Approach Comparison (Actual Benchmark Results)

| Phase | Full-Scan | Parameter-First |
|-------|-----------|-----------------|
| parameter_configurations scan | N/A | 180 rows (SQL json_extract) |
| SQL rows read from simulation_results | 313,020 | 6,956 |
| SQL execution | 1,157ms | 251ms |
| Python JSON deserializations | 626,040 (313K params + 313K stats) | 6,956 (stats only) |
| Python JSON parse + filter | 1,113ms | 38ms |
| Grid construction | 0.7ms | 0.6ms |
| **Actual total** | **2,271ms** | **290ms** |
| Peak memory | 155.9MB | 3.6MB |

**Measured speedup**: 7.8× for a single parameter selection.

### Benchmark Requirement (Stage 1)

Stage 1 includes a benchmark gate that runs the **actual implementation** against the Stage 0 baseline:

**Baseline**: The Stage 0 full-scan measurement (2,271ms, 313K rows, 626K JSON parses).

**Candidate**: The actual `get_cohort_horizon_grid()` implementation from Stage 1, measured with the same ERN-scale fixture.

**Acceptance criteria**:
- Matching result set equals baseline result set
- Rows read substantially less than full scan (target: <10K)
- JSON parses substantially less than full scan (target: <10K)
- Wall time materially below baseline

No hard speedup ratio requirement — SQLite and hardware variability make exact ratios inappropriate.

### API Cost

| Phase | Operation | Estimated Cost |
|-------|-----------|---------------|
| Serialization | Pydantic model → JSON | ~10ms |
| Payload | ~210KB for 6,956 cells | ~5ms network |
| **Total API** | | **~15ms** |

### Browser Rendering

| Phase | Operation | Estimated Cost |
|-------|-----------|---------------|
| Fetch | 210KB payload | ~50ms |
| Parse JSON | 210KB | ~5ms |
| Chart.js matrix render | 6,956 cells on canvas | ~100ms |
| **Total Browser** | | **~155ms** |

---

## G. Visualization Decision

### Selected: Matrix Heatmap (chartjs-chart-matrix)

**Why heatmap is appropriate:**

1. **Binary success/failure** maps naturally to a two-color scale (green/red)
2. **2D grid structure** (cohorts × horizons) is the canonical heatmap use case
3. **Visual pattern recognition** — the human eye can instantly spot clusters of failures
4. **Consistent with existing placeholder** — `build_empty_cohort_chart()` already declares `chart_type="heatmap"`

**Why not alternatives:**

| Alternative | Rejection Reason |
|-------------|-----------------|
| Survival curve (line chart) | Shows one cohort at a time; cannot see the full grid |
| Bar chart (success rate by cohort) | Loses horizon dimension; requires separate charts per horizon |
| Table with conditional formatting | Less visual impact; harder to spot patterns |
| Interactive grid (HTML) | More complex; breaks the Chart.js pipeline |
| Scatter plot | Not suitable for categorical grid cells |

**Chart.js plugin**: `chartjs-chart-matrix@2.0.1` (CDN, ~15KB gzipped)

This plugin is well-maintained, supports:
- Matrix cells with configurable colors
- Tooltips with custom callbacks
- Axis labels and tick formatting
- Responsive sizing

### Chart Configuration

```javascript
{
    type: 'matrix',
    data: {
        datasets: [{
            data: [
                { x: horizon_idx, y: cohort_idx, v: success ? 1 : 0 },
                ...
            ],
            backgroundColor(ctx) {
                return ctx.dataset.data[ctx.dataIndex].v === 1
                    ? 'rgba(34, 197, 94, 0.7)'   // green
                    : 'rgba(239, 68, 68, 0.7)';  // red
            },
            width: ({ chart }) => (chart.chartArea.width / numHorizons) - 1,
            height: ({ chart }) => (chart.chartArea.height / numCohorts) - 0.5,
        }]
    },
    options: {
        scales: {
            x: { type: 'linear', ticks: { callback: (v) => horizons[v] + 'Y' } },
            y: { type: 'linear', ticks: { callback: (v) => cohorts[v] } },
        },
        plugins: {
            tooltip: {
                callbacks: {
                    title: (items) => cohorts[items[0].parsed.y],
                    label: (item) => {
                        const d = item.dataset.data[item.dataIndex];
                        return horizons[d.x] + 'Y: ' + (d.v ? 'Success' : 'Failed');
                    },
                },
            },
        },
    },
}
```

### Color Semantics

| Color | Meaning | Hex |
|-------|---------|-----|
| Green | Success (portfolio survived full horizon) | `rgba(34, 197, 94, 0.7)` |
| Red | Failure (portfolio depleted before horizon end) | `rgba(239, 68, 68, 0.7)` |

No misleading thresholds. Binary classification maps to binary color scale.

---

## H. API Contract

### Endpoints

#### 1. List Available Parameters

```
GET /api/v1/persistence/results/{result_id}/parameters
```

**Response:**

```python
class ParameterSelectorDTO(BaseModel):
    equity_allocation: float
    withdrawal_rate: float

class AvailableParametersDTO(BaseModel):
    result_id: str
    parameters: list[ParameterSelectorDTO]
```

**Purpose**: Populates the parameter selector dropdown. Returns unique `(equity_allocation, withdrawal_rate)` selectors. The frontend fetches this first, then lets the user select a selector before fetching the grid.

**Example** (ERN): 45 selectors (5 equity × 9 withdrawal rates), not 180 horizon-specific entries.

#### 2. Get Cohort Grid

```
GET /api/v1/persistence/results/{result_id}/cohort-grid?equity_allocation=0.5&withdrawal_rate=0.04
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `equity_allocation` | float | Yes | Equity allocation to filter by |
| `withdrawal_rate` | float | Yes | Withdrawal rate to filter by |

Both parameters are required. If omitted, return 400 INVALID_PARAMETERS.

**Response:**

```python
class CohortGridDataDTO(BaseModel):
    success: list[list[bool]]           # [cohort_idx][horizon_idx]
    failure_month: list[list[int | None]]
    terminal_wealth: list[list[float]]

class CohortGridDTO(BaseModel):
    result_id: str
    cohorts: list[str]                  # sorted ISO date strings
    horizons: list[int]                 # sorted horizon years (derived from matching configs)
    parameters: dict[str, float]        # {"equity_allocation": 0.5, "withdrawal_rate": 0.04}
    grid: CohortGridDataDTO
    total_units: int
    success_count: int
    failure_count: int
```

### Error Responses

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `RESULT_NOT_FOUND` | Result ID does not exist |
| 400 | `INVALID_PARAMETERS` | Required query parameters missing or invalid |
| 400 | `PARAMETER_NOT_FOUND` | No units match the requested (equity_allocation, withdrawal_rate) |
| 200 | (empty grid) | Result exists but grid has 0 cohorts (should not occur with valid data) |

The distinction between 404 and 400 is important:
- **404**: The result itself does not exist. The user may have a wrong result ID.
- **400**: The result exists but the parameter selection is invalid. The user should choose different parameters.

### Ordering

- `parameters`: By equity_allocation, then withdrawal_rate (all ascending)
- `cohorts`: Chronological (earliest first)
- `horizons`: Ascending (shortest first)
- Grid arrays: Aligned with `cohorts` and `horizons` indices

### Parameter Selection Strategy

The `equity_allocation` and `withdrawal_rate` parameters are **required** on the cohort-grid endpoint. This forces explicit selection rather than relying on an arbitrary default.

The `/parameters` endpoint provides the list of valid selectors. The frontend flow is:

```
1. GET /results/{id}/parameters  →  list of valid (equity_allocation, withdrawal_rate) pairs
2. User selects one from dropdown
3. GET /results/{id}/cohort-grid?equity_allocation=X&withdrawal_rate=Y  →  grid data (all horizons)
```

---

## I. Architecture

```
SQLiteRepository (fbf-core)
  ├── get_available_parameters()     — parameter selector listing
  ├── get_cohort_horizon_grid()      — parameter-first filtered query
  ↓
PersistenceService (fbf-ui)
  ├── get_result_parameters()  → AvailableParametersDTO
  ├── get_result_cohort_grid() → CohortGridDTO
  ↓
API Endpoints (fbf-ui)
  ├── GET /results/{id}/parameters
  ├── GET /results/{id}/cohort-grid?equity_allocation=&withdrawal_rate=
  ↓
ResultVisualizationTransformer (fbf-ui)
  ├── build_cohort_heatmap() → ChartSpecDTO (matrix)
  ↓
Frontend (results/detail.html)
  ├── chartjs-chart-matrix plugin
  ├── Parameter selector dropdowns
  ├── renderCohortHeatmap(data)
  └── Canvas-based matrix rendering
```

### Layer Responsibilities

| Layer | Owns | Does NOT Own |
|-------|------|-------------|
| **Core** | SQL queries, parameter configuration filtering, JOIN logic, JSON parsing, Python grouping | Chart types, color schemes, API DTOs |
| **PersistenceService** | DTO conversion, parameter validation, None→error mapping | SQL, aggregation logic |
| **API** | HTTP routing, query param parsing, error responses, parameter validation | Business logic, data transformation |
| **Transformer** | ChartSpecDTO construction, label formatting, color mapping | Financial calculations, data aggregation |
| **Frontend** | Chart.js rendering, tooltips, parameter selector interaction, user flow | Data fetching logic (delegated to API) |

---

## J. P10 Integration

### Dashboard Extension

P11 adds a new card section to the existing P10 results dashboard (`results/detail.html`):

```
results/detail.html
  ├── summary-card          (P10)
  ├── wealth-card           (P10)
  ├── failure-card          (P10)
  ├── trajectory-card       (P10)
  ├── cohort-card           (P11 — NEW)
  │   ├── parameter selector dropdowns (equity_allocation, withdrawal_rate)
  │   ├── canvas#cohort-chart
  │   └── loading/empty/error states
  └── error-card            (P10)
```

### Navigation

No navigation changes. P11 is a new section within the existing results dashboard. Users reach it via the same path:

```
/persistence → /persistence/experiments/{id} → /results/{id} → cohort heatmap section
```

### Loading Sequence

```javascript
async function loadResultDashboard() {
    await Promise.all([
        loadSummary(),
        loadStatistics(),
        loadTrajectory(),
        loadCohortParameters(),    // P11 — NEW: fetch available parameter selectors
    ]);
}

async function loadCohortParameters() {
    const response = await fetch('/api/v1/persistence/results/' + RESULT_ID + '/parameters');
    if (!response.ok) {
        if (response.status === 404) return;  // result not found, cohort card stays hidden
        throw new Error('Parameters API returned ' + response.status);
    }
    const data = await response.json();
    renderParameterSelectors(data.parameters);
    // Auto-select first selector and load grid
    loadCohortGrid(data.parameters[0]);
}

async function loadCohortGrid(params) {
    const url = '/api/v1/persistence/results/' + RESULT_ID + '/cohort-grid'
        + '?equity_allocation=' + params.equity_allocation
        + '&withdrawal_rate=' + params.withdrawal_rate;
    const response = await fetch(url);
    if (!response.ok) {
        if (response.status === 404 || response.status === 400) {
            showCohortEmpty();
            return;
        }
        throw new Error('Cohort grid API returned ' + response.status);
    }
    const data = await response.json();
    renderCohortHeatmap(data);
}
```

### Backward Compatibility

P10 visualizations are not modified. The new cohort card is purely additive. The `loadCohortParameters()` function handles 404 gracefully (card remains hidden if no data).

---

## K. Risks

### Scalability Risks

| Risk | Mitigation |
|------|-----------|
| Large payload for full grid (1,739 × 4 = 6,956 cells) | Payload is ~210KB; well within browser limits. |
| 1,739 cohort labels on y-axis | Use tick sampling (show every Nth label). Canvas rendering handles this. |

### Correctness Risks

| Risk | Mitigation |
|------|-----------|
| unit_index misalignment between simulation_results and planned_units | The UNIQUE(plan_id, unit_index) constraint ensures 1:1 mapping. Existing `get_export_data` proves this works. |
| params_json parsing variation | Canonical serialization (sorted keys, compact separators) ensures deterministic output. |
| Missing statistics_payload_json for non-final rows | Filter to `final_month = 1` only. Same as existing `get_result_statistics`. |

### UX Risks

| Risk | Mitigation |
|------|-----------|
| 1,739 rows too dense to read | Tooltip shows individual cell details. Tick sampling reduces label density. |
| Parameter selector requires extra load step | First endpoint is lightweight (45 rows, ~1KB). Can be cached. |
| chartjs-chart-matrix CDN dependency | Pin version (2.0.1). ~15KB gzipped. Well-maintained. |

### Dependency Risks

| Risk | Mitigation |
|------|-----------|
| chartjs-chart-matrix compatibility with Chart.js 4.x | Plugin v2.0.1 explicitly supports Chart.js 4.x. Verified. |
| Plugin CDN availability | Pin specific version. Fallback: embed inline if CDN fails. |

---

## L. Alternatives Considered

### Alternative 1: Success Rate Bar Chart (by cohort)

**Concept**: For each cohort, compute success rate across all horizons. Show as bar chart.

**Rejection**: Loses the horizon dimension. The whole point of P11 is to see how results vary across BOTH cohort AND horizon simultaneously.

### Alternative 2: Survival Curve Overlay

**Concept**: For each cohort, plot a survival curve (probability of success over time).

**Rejection**: Requires probability estimation across parameter sets. More complex, less direct. The matrix heatmap is the canonical representation for this research question.

### Alternative 3: Aggregate Across Parameters

**Concept**: For each (cohort, horizon) cell, compute success rate across ALL parameter configurations.

**Rejection**: Loses the parameter dimension. The success rate depends heavily on (equity_allocation, withdrawal_rate). Aggregating across parameters produces a misleading average. The user should see one parameter set at a time.

### Alternative 4: HTML Table with CSS

**Concept**: Render the grid as an HTML table with conditional cell coloring.

**Rejection**: 1,739 rows × 4 columns = 6,956 DOM elements. Slower than canvas rendering. Breaks the Chart.js pipeline. No interactive tooltips without custom JavaScript.

### Alternative 5: Server-Side Downsampling

**Concept**: Group cohorts by decade, reducing rows from 1,739 to ~15.

**Rejection**: Loses individual cohort detail. The fine-grained structure (which specific months are dangerous) is the key insight. Can be added as a future enhancement.

### Alternative 6: Full-Scan with Python Filtering (Original Design)

**Concept**: Read all 313K rows, parse all JSON, filter by parameters in Python.

**Rejection**: Reads 45× more simulation data than necessary. Parameter-first resolution via SQL `json_extract` filtering is strictly superior: fewer rows read, fewer JSON parses, faster execution. The 180-row parameter configuration scan is negligible compared with 313K simulation rows.

---

## M. Implementation Plan

### Stage 0: ERN-Scale Benchmark — COMPLETE

**Objective**: Establish baseline performance and validate parameter-first approach at ERN scale.

**Approach**:
1. Created a temporary benchmark script that builds an in-memory SQLite database with ERN-scale data (313K units, 180 parameter configs, 1,739 cohorts)
2. Implemented both query approaches:
   - **Baseline**: Read all final_month=1 rows, parse all JSON (params + stats), filter in Python
   - **Candidate**: json_extract subset match → param_config_ids → filtered SQL read → parse matching stats only
3. Measured and reported: wall-clock time, rows read, JSON deserializations, peak memory
4. Removed benchmark script after measurement

**Files affected**: Temporary benchmark script only (removed after measurement)

**Benchmark Results**:

| Metric | Full-Scan | Parameter-First | Ratio |
|--------|-----------|-----------------|-------|
| Rows read | 313,020 | 6,956 | 45× fewer |
| Python JSON parses | 626,040 (313K params + 313K stats) | 6,956 (stats only) | 90× fewer |
| SQL execution | 1,157ms | 251ms | 4.6× faster |
| JSON parse + filter | 1,113ms | 38ms | 29× faster |
| **Total wall-clock** | **2,271ms** | **290ms** | **7.8× faster** |
| Peak memory | 155.9MB | 3.6MB | 43.6× less |

**Hash semantics verified**:
- Canonical JSON deterministic: YES
- SHA-256 hash deterministic: YES
- All 180 configs hash-verified: YES
- `json_extract` subset match works: YES (4 configs for eq=0.5, wr=0.04)
- Correctness match: 6,956 units == 6,956 units PASS

**JSON deserialization explanation**: The full-scan approach parses 626,040 JSON payloads because it deserializes both `params_json` (to filter by equity/withdrawal) and `statistics_payload_json` (to extract success data) for every one of the 313,020 rows. The parameter-first approach avoids `params_json` Python deserialization entirely — SQL `json_extract()` handles parameter filtering at the database level. Only the 6,956 matching `statistics_payload_json` payloads are parsed in Python.

**Acceptance criteria**: Both approaches produce identical results. Candidate is measurably faster (7.8×). Benchmark results documented. **COMPLETE**.

### Stage 1: Core Repository Methods

**Objective**: Add `get_available_parameters()` and `get_cohort_horizon_grid()` to `SQLiteRepository`.

**Files affected**:
- `fbf-core/src/fbf/core/persistence/studies/sqlite/sqlite_repository.py`

**Implementation notes**:
- `get_available_parameters()` returns unique `(equity_allocation, withdrawal_rate)` selectors, not horizon-specific entries
- `get_cohort_horizon_grid()` filters `parameter_configurations` by `json_extract` to resolve matching `param_config_id`s, then reads only matching `simulation_results`
- No use of `params_hash` for partial parameter selection — the full hash represents all 3 params including horizon
- `horizons` in the grid response are derived from the matching configurations, not passed as input

**Tests**:
- `fbf-core/tests/unit/test_sqlite_repository.py` — new test classes:

  `TestAvailableParameters`:
  - Returns unique (equity_allocation, withdrawal_rate) selectors for a result
  - Returns None for missing result_id
  - Correct parameter values parsed from params_json
  - Ordering: by equity_allocation, withdrawal_rate
  - Deterministic output for same input
  - Multiple horizons for one (equity, withdrawal) selector produce exactly one entry
  - Result belonging to another plan does not leak selectors

  `TestCohortHorizonGrid`:
  - Single cohort, single horizon, success
  - Single cohort, single horizon, failure
  - Multiple cohorts, multiple horizons, mixed results
  - Filter by equity_allocation + withdrawal_rate (returns all horizons)
  - Returns None for missing result_id
  - Returns None for non-matching parameter filter
  - Ordering: chronological cohorts, ascending horizons
  - Deterministic output for same input
  - No duplicate cells
  - No missing cells for complete grid
  - Result belonging to another plan does not leak units

**Benchmark gate**: Run the actual `get_cohort_horizon_grid()` implementation against the Stage 0 ERN-scale fixture. Verify:
- Matching result set equals baseline
- Rows read < 10K (vs 313K full scan)
- JSON parses < 10K (vs 626K full scan)
- Wall time materially below 2,271ms baseline

**Acceptance criteria**: All new tests pass. Existing Core tests still pass. Benchmark gate passes. Ruff clean. mypy --strict clean.

### Stage 2: PersistenceService + DTOs

**Objective**: Add `AvailableParametersDTO`, `CohortGridDTO`, and corresponding `PersistenceService` methods.

**Files affected**:
- `fbf-ui/src/fbf/ui/orchestration/persistence_service.py`

**DTO changes**:
- `ParameterSelectorDTO` contains `equity_allocation` and `withdrawal_rate` (no `horizon_years`)
- `CohortGridDTO` contains `horizons` as a top-level field (derived from matching configurations)

**Tests**:
- `fbf-ui/tests/unit/test_persistence_service.py` — new tests:
  - `get_result_parameters()` returns AvailableParametersDTO with unique selectors
  - `get_result_parameters()` returns None for missing result
  - `get_result_cohort_grid()` returns CohortGridDTO
  - `get_result_cohort_grid()` returns None for missing result
  - `get_result_cohort_grid()` returns None for non-matching parameters
  - Grid structure matches expected shape
  - Horizons in grid response match all horizons for the selected (equity, withdrawal)

**Acceptance criteria**: All tests pass. Ruff clean. mypy --strict clean.

### Stage 3: API Endpoints

**Objective**: Add `GET /results/{id}/parameters` and `GET /results/{id}/cohort-grid` endpoints.

**Files affected**:
- `fbf-ui/src/fbf/ui/api/persistence.py`

**Tests**:
- `fbf-ui/tests/unit/test_p10_persistence_api.py` — new test classes:

  `TestAvailableParametersEndpoint`:
  - 200 with valid result and seeded data
  - 404 for missing result
  - Response schema validation
  - Returns unique (equity, withdrawal) selectors

  `TestCohortGridEndpoint`:
  - 200 with valid result and seeded data
  - 404 for missing result
  - 400 for missing equity_allocation
  - 400 for missing withdrawal_rate
  - 400 for non-matching parameter filter
  - Response schema validation
  - Ordering verification
  - Horizons in response match all horizons for the selected parameters

**Acceptance criteria**: All tests pass. Ruff clean. mypy --strict clean.

### Stage 4: Transformer

**Objective**: Implement `build_cohort_heatmap()` on `ResultVisualizationTransformer`.

**Files affected**:
- `fbf-ui/src/fbf/ui/visualization/transformers.py`

**Tests**:
- `fbf-ui/tests/unit/test_p10_visualization_transformers.py` — new test class `TestCohortHeatmap`:
  - Chart type is "matrix"
  - Correct number of data points (cohorts × horizons)
  - Labels match input cohorts/horizons
  - Success cells colored green, failure cells colored red
  - Empty grid produces empty chart
  - Single cohort, single horizon
  - Custom title
  - Reproducibility envelope present

**Acceptance criteria**: All tests pass. Ruff clean. mypy --strict clean.

### Stage 5: Frontend Integration

**Objective**: Render cohort heatmap in results dashboard with parameter selectors.

**Files affected**:
- `fbf-ui/src/fbf/ui/presentation/templates/results/detail.html`

**Tests**:
- `fbf-ui/tests/unit/test_p10_stage4_frontend.py` — new tests:
  - Cohort card present in HTML
  - Canvas element `cohort-chart` present
  - chartjs-chart-matrix CDN script included
  - `loadCohortParameters` and `loadCohortGrid` functions defined
  - Parameter selector elements present
  - API endpoints accessible (404 for missing data)
  - Selectors contain unique (equity, withdrawal) pairs, not 180 horizon-specific entries

**Acceptance criteria**: All tests pass. Ruff clean. mypy --strict clean.

### Stage 6: Playwright Browser Verification

**Objective**: Real browser verification of cohort heatmap rendering.

**Files affected**:
- `fbf-ui/tests/unit/test_p10_stage4_frontend.py` — Playwright tests

**Tests**:
- Dashboard loads with cohort card visible (when data exists)
- Parameter selectors are interactive
- Changing selected (equity, withdrawal) combination changes the grid while retaining the complete horizon axis
- Heatmap canvas renders without JavaScript errors
- Tooltip appears on cell hover
- Empty state handled gracefully
- Navigation from persistence browser works

**Acceptance criteria**: All Playwright checks pass. 0 JavaScript errors.

---

## N. Explicit Decision

**APPROVE DESIGN (Revised v2)**

The revised P11 design addresses all feedback points:

1. **Parameter-first resolution**: Uses SQL `json_extract` filtering on the tiny `parameter_configurations` table (180 rows) to resolve matching `param_config_id`s, then reads only matching simulation results. Processes ~6,956 rows instead of 313K for ERN.
2. **No incorrect hash usage**: `params_hash` is not used for partial parameter selection. The full hash represents all 3 params including `horizon_years`. Partial selection uses `json_extract` subset match.
3. **Clean selector semantics**: `/parameters` returns unique `(equity_allocation, withdrawal_rate)` selectors (45 for ERN), not 180 horizon-specific entries. Horizons are derived from matching configurations and returned in the grid response.
4. **Benchmark required**: Stage 0 establishes actual performance baseline. Stage 1 benchmark gate runs the real implementation against this baseline.
5. **Distinct error conditions**: 404 (result not found) vs 400 (invalid/missing parameters) vs 400 (parameter not found).
6. **No schema changes**: Leverages existing `params_json` structure and `json_extract` for filtering.
7. **Generic and reusable**: Works for any study with cohort × horizon structure.

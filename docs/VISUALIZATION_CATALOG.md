# Visualization Catalog — fbf-ui

This document defines the analytical taxonomy, data requirements, derived metrics, and visual specifications for interactive financial charts in `fbf-ui`.

---

## 1. Historical Cohort Heatmap & Timeline

### Description
Visualizes backtest performance across starting calendar cohorts (e.g. 1871–2026) to identify historical failure periods (e.g. 1929 Great Depression, 1966 Stagflation, 1999 Dot-com bubble).

### Requirements Specification
- **Required Raw Data**: Monthly portfolio balances per cohort from `ResearchExecutionResult`.
- **Derived Metrics**: Ending portfolio value, minimum portfolio value (drawdown), success/failure boolean flag per cohort.
- **Aggregation Rules**: Grouped by retirement start month (`YYYY-MM`).
- **Axes**:
  - **X-axis**: Start Year (1871–present).
  - **Y-axis**: Start Month (Jan–Dec) or Duration Horizon (10, 20, 30, 40, 50 years).
  - **Color Scale (Z-axis)**: Terminal Wealth Ratio ($W_{final} / W_{initial}$) or SWR %.
- **Units**: Percentage (%) or Real Dollar Ratio.
- **Execution Modes**: Decimal Fast Path, Reference Pipeline.
- **Persistence Requirements**: Stored study experiment or non-persistent session.
- **Core Availability**: Raw cohort trajectories exist in `fbf-core`. Cohort aggregation view models built in `fbf.ui.visualization.transformers`.

---

## 2. Safe Withdrawal Rate (SWR) Sensitivity Curve

### Description
Displays maximum sustainable safe withdrawal rate vs failure probability or retirement duration.

### Requirements Specification
- **Required Raw Data**: `StudyPlanResult` or `optimize_study_swr` output grid.
- **Derived Metrics**: Max SWR (%), Failure Rate (%), Capital Preservation Rate (%).
- **Axes**:
  - **X-axis**: Withdrawal Rate (% per annum, e.g. 3.0% to 6.0% in 0.1% steps).
  - **Y-axis**: Success Rate (%) or Terminal Wealth Percentile.
- **Units**: Percentage (%).
- **Execution Modes**: SWR Optimization solver (`optimize_study_swr`).
- **Core Availability**: Fully supported in `fbf-core` via `optimize_study_swr`.

---

## 3. Capital Preservation & Depletion Distribution

### Description
Histogram and boxplot showing final wealth distribution across historical cohorts for a specific withdrawal policy.

### Requirements Specification
- **Required Raw Data**: Cohort terminal wealth list ($W_{final}$).
- **Derived Metrics**: P10, P25, P50 (median), P75, P90 terminal wealth, Probability of Capital Depletion ($W_{final} = 0$), Probability of Real Capital Preservation ($W_{final} \ge W_{initial}$).
- **Axes**:
  - **X-axis**: Terminal Wealth Bins (Real USD).
  - **Y-axis**: Cohort Frequency / Percentage.
- **Units**: Real USD ($).
- **Core Availability**: Supported in `fbf-core` `ResearchExecutionResult`.

---

## 4. Valuation Bucket Sensitivity (CAPE / Shiller P/E)

### Description
Categorizes retirement outcomes based on initial CAPE / Valuation regime at start of retirement.

### Requirements Specification
- **Required Raw Data**: Initial valuation metric per cohort (from dataset), cohort success flag.
- **Derived Metrics**: Conditional success rate per valuation quartile/bucket.
- **Axes**:
  - **X-axis**: Initial CAPE Bucket (<15, 15-20, 20-25, 25-30, >30).
  - **Y-axis**: Safe Withdrawal Rate (%) or Failure Probability (%).
- **Units**: Valuation Multiple (Ratio) vs Percentage (%).
- **Core Availability**: Datasets contain CAPE values; regime bucketing implemented in UI visualization adapter.

---

## 5. Equity Glidepath Analysis

### Description
Compares static equity allocations vs dynamic/linear equity glidepaths (e.g. 60/40 static vs 60->80 glidepath).

### Requirements Specification
- **Required Raw Data**: Multi-strategy `ResearchExecutionResult` set.
- **Derived Metrics**: Comparative SWR, Min Portfolio Drawdown, Median Terminal Wealth.
- **Axes**:
  - **X-axis**: Time Horizon (Months/Years in Retirement).
  - **Y-axis**: Asset Class Weight (%) & Portfolio Balance ($).
- **Core Availability**: Multi-strategy execution supported via `execute_study_plan`.

---

## 6. Multi-Strategy Comparator Dashboard

### Description
Side-by-side comparison of multiple backtest studies or persisted database experiments.

### Requirements Specification
- **Required Raw Data**: Experiment results from `SQLiteRepository`.
- **Derived Metrics**: Metric delta table (SWR delta, failure rate delta, terminal wealth distribution comparison).
- **Visual Forms**: Multi-line trajectory overlays, side-by-side metric cards, differential cohort heatmaps.
- **Core Availability**: Queryable from `SQLiteRepository`.

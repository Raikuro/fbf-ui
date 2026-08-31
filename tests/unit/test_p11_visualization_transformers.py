"""P11 Stage 4 tests: cohort heatmap transformer."""

from __future__ import annotations

from fbf.ui.orchestration.persistence_service import (
    CohortGridDataDTO,
    CohortGridDTO,
)
from fbf.ui.visualization import ResultVisualizationTransformer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cohort_grid(
    cohorts: list[str] | None = None,
    horizons: list[int] | None = None,
    success: list[list[bool]] | None = None,
    failure_month: list[list[int | None]] | None = None,
    terminal_wealth: list[list[float]] | None = None,
) -> CohortGridDTO:
    if cohorts is None:
        cohorts = ["2000-01-01", "2001-01-01", "2002-01-01"]
    if horizons is None:
        horizons = [30, 40]
    n_cohorts = len(cohorts)
    n_horizons = len(horizons)
    if success is None:
        success = [
            [(hash(f"{r}-{c}") % 3) != 0 for c in range(n_horizons)]
            for r in range(n_cohorts)
        ]
    if failure_month is None:
        failure_month = [
            [None if success[r][c] else (hash(f"fm-{r}-{c}") % 360) + 1
             for c in range(n_horizons)]
            for r in range(n_cohorts)
        ]
    if terminal_wealth is None:
        terminal_wealth = [
            [0.0 if not success[r][c] else float(500000 + hash(f"tw-{r}-{c}") % 500000)
             for c in range(n_horizons)]
            for r in range(n_cohorts)
        ]
    return CohortGridDTO(
        result_id="test-result",
        cohorts=cohorts,
        horizons=horizons,
        parameters={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        grid=CohortGridDataDTO(
            success=success,
            failure_month=failure_month,
            terminal_wealth=terminal_wealth,
        ),
        total_units=n_cohorts * n_horizons,
        success_count=sum(1 for row in success for v in row if v),
        failure_count=sum(1 for row in success for v in row if not v),
    )


# ===========================================================================
# 1. Empty Input
# ===========================================================================


class TestEmptyInput:
    def test_empty_cohorts(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=[], success=[], failure_month=[], terminal_wealth=[])
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.chart_type == "heatmap"
        assert chart.labels == []
        assert chart.datasets == []

    def test_empty_horizons(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            horizons=[], success=[[], [], []],
            failure_month=[[], [], []], terminal_wealth=[[], [], []],
        )
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.chart_type == "heatmap"
        assert chart.labels == []
        assert chart.datasets == []

    def test_empty_chart_matches_empty_cohort_chart(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=[], success=[], failure_month=[], terminal_wealth=[])
        chart = transformer.build_cohort_heatmap(grid)
        empty_chart = transformer.build_empty_cohort_chart()
        assert chart.labels == empty_chart.labels
        assert chart.datasets == empty_chart.datasets
        assert chart.chart_type == empty_chart.chart_type


# ===========================================================================
# 2. Deterministic Output
# ===========================================================================


class TestDeterministicOutput:
    def test_same_input_same_output(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart1 = transformer.build_cohort_heatmap(grid)
        chart2 = transformer.build_cohort_heatmap(grid)
        assert chart1.labels == chart2.labels
        assert chart1.datasets == chart2.datasets

    def test_chart_type_is_heatmap(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.chart_type == "heatmap"

    def test_axis_labels(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.x_axis_label == "Start Year"
        assert chart.y_axis_label == "Horizon (Years)"

    def test_custom_title(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid, title="Custom Title")
        assert chart.title == "Custom Title"

    def test_default_title(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.title == "Cohort × Horizon Heatmap"


# ===========================================================================
# 3. Label Extraction
# ===========================================================================


class TestLabelExtraction:
    def test_year_labels_extracted(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=["2000-01-01", "2005-06-15", "2010-12-31"])
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.labels == ["2000", "2005", "2010"]

    def test_short_date_handled(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=["2000", "2001"])
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.labels == ["2000", "2001"]

    def test_preserves_cohort_order(self) -> None:
        transformer = ResultVisualizationTransformer()
        cohorts = ["2010-01-01", "2000-01-01", "2005-01-01"]
        grid = _make_cohort_grid(cohorts=cohorts)
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.labels == ["2010", "2000", "2005"]


# ===========================================================================
# 4. Dataset Structure
# ===========================================================================


class TestDatasetStructure:
    def test_one_dataset_per_horizon(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(horizons=[30, 40, 50])
        chart = transformer.build_cohort_heatmap(grid)
        assert len(chart.datasets) == 3

    def test_dataset_labels_match_horizons(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(horizons=[30, 40])
        chart = transformer.build_cohort_heatmap(grid)
        labels = [d.label for d in chart.datasets]
        assert labels == ["30y", "40y"]

    def test_dataset_data_shape(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=["2000-01-01", "2001-01-01"], horizons=[30, 40])
        chart = transformer.build_cohort_heatmap(grid)
        for dataset in chart.datasets:
            assert len(dataset.data) == 2


# ===========================================================================
# 5. Success/Failure Encoding
# ===========================================================================


class TestSuccessFailureEncoding:
    def test_success_encodes_as_1(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            success=[[True]],
            failure_month=[[None]],
            terminal_wealth=[[500000.0]],
            cohorts=["2000-01-01"],
            horizons=[30],
        )
        chart = transformer.build_cohort_heatmap(grid)
        cell = chart.datasets[0].data[0]
        assert cell["value"] == 1

    def test_failure_encodes_as_0(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            success=[[False]],
            failure_month=[[24]],
            terminal_wealth=[[0.0]],
            cohorts=["2000-01-01"],
            horizons=[30],
        )
        chart = transformer.build_cohort_heatmap(grid)
        cell = chart.datasets[0].data[0]
        assert cell["value"] == 0

    def test_mixed_success_failure(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            success=[[True, False], [False, True]],
            failure_month=[[None, 12], [36, None]],
            terminal_wealth=[[500000.0, 0.0], [0.0, 600000.0]],
            cohorts=["2000-01-01", "2001-01-01"],
            horizons=[30, 40],
        )
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.datasets[0].data[0]["value"] == 1
        assert chart.datasets[0].data[1]["value"] == 0
        assert chart.datasets[1].data[0]["value"] == 0
        assert chart.datasets[1].data[1]["value"] == 1


# ===========================================================================
# 6. Tooltip Data
# ===========================================================================


class TestTooltipData:
    def test_tooltips_in_cells(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid)
        for dataset in chart.datasets:
            for cell in dataset.data:
                assert "tooltip" in cell

    def test_tooltip_count_matches_cells(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=["2000-01-01", "2001-01-01"], horizons=[30, 40])
        chart = transformer.build_cohort_heatmap(grid)
        total_cells = sum(len(d.data) for d in chart.datasets)
        assert total_cells == 4

    def test_tooltip_contains_year(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=["2005-01-01"], horizons=[30])
        chart = transformer.build_cohort_heatmap(grid)
        tooltip = chart.datasets[0].data[0]["tooltip"]
        assert "2005" in tooltip

    def test_tooltip_contains_horizon(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(cohorts=["2000-01-01"], horizons=[40])
        chart = transformer.build_cohort_heatmap(grid)
        tooltip = chart.datasets[0].data[0]["tooltip"]
        assert "40y" in tooltip

    def test_tooltip_failure_month_none(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            cohorts=["2000-01-01"], horizons=[30],
            success=[[True]], failure_month=[[None]], terminal_wealth=[[500000.0]],
        )
        chart = transformer.build_cohort_heatmap(grid)
        tooltip = chart.datasets[0].data[0]["tooltip"]
        assert "N/A" in tooltip

    def test_tooltip_failure_month_value(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            cohorts=["2000-01-01"], horizons=[30],
            success=[[False]], failure_month=[[24]], terminal_wealth=[[0.0]],
        )
        chart = transformer.build_cohort_heatmap(grid)
        tooltip = chart.datasets[0].data[0]["tooltip"]
        assert "24" in tooltip

    def test_tooltip_wealth_formatted(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            cohorts=["2000-01-01"], horizons=[30],
            success=[[True]], failure_month=[[None]], terminal_wealth=[[1234567.0]],
        )
        chart = transformer.build_cohort_heatmap(grid)
        tooltip = chart.datasets[0].data[0]["tooltip"]
        assert "1,234,567" in tooltip


# ===========================================================================
# 7. Ordering Preservation
# ===========================================================================


class TestOrderingPreservation:
    def test_dataset_order_matches_horizon_order(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(horizons=[50, 30, 40])
        chart = transformer.build_cohort_heatmap(grid)
        labels = [d.label for d in chart.datasets]
        assert labels == ["50y", "30y", "40y"]

    def test_data_corresponds_to_correct_horizon(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            cohorts=["2000-01-01"], horizons=[30, 40],
            success=[[True, False]],
            failure_month=[[None, 24]],
            terminal_wealth=[[500000.0, 0.0]],
        )
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.datasets[0].data[0]["value"] == 1
        assert chart.datasets[1].data[0]["value"] == 0


# ===========================================================================
# 8. Reproducibility Envelope
# ===========================================================================


class TestReproducibilityEnvelope:
    def test_envelope_present(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.reproducibility is not None

    def test_execution_mode(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid()
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.reproducibility.execution_mode == "COHORT_HEATMAP"


# ===========================================================================
# 9. Single Cohort × Single Horizon
# ===========================================================================


class TestSingleCohortSingleHorizon:
    def test_1x1_grid(self) -> None:
        transformer = ResultVisualizationTransformer()
        grid = _make_cohort_grid(
            cohorts=["2000-01-01"], horizons=[30],
            success=[[True]], failure_month=[[None]], terminal_wealth=[[500000.0]],
        )
        chart = transformer.build_cohort_heatmap(grid)
        assert chart.labels == ["2000"]
        assert len(chart.datasets) == 1
        cell = chart.datasets[0].data[0]
        assert cell["value"] == 1
        assert "tooltip" in cell

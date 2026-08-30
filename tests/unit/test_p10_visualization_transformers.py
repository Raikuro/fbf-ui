"""P10 Stage 3 tests: visualization transformers for results dashboard."""

from __future__ import annotations

from fbf.ui.orchestration.persistence_service import (
    FailureMonthBucketDTO,
    FailureMonthsHistogramDTO,
    MaxDrawdownStatsDTO,
    ResultStatisticsDTO,
    TerminalWealthStatsDTO,
    TrajectoryDTO,
)
from fbf.ui.visualization import ResultVisualizationTransformer
from fbf.ui.visualization.models import SummaryCardDTO

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_statistics(
    total_units: int = 100,
    success_count: int = 85,
    failure_count: int = 15,
    terminal_wealth: TerminalWealthStatsDTO | None = None,
    failure_months: FailureMonthsHistogramDTO | None = None,
    max_drawdown: MaxDrawdownStatsDTO | None = None,
) -> ResultStatisticsDTO:
    if terminal_wealth is None:
        terminal_wealth = TerminalWealthStatsDTO(
            min=45000.0, p10=48000.0, p25=52000.0,
            median=60000.0, p75=68000.0, p90=72000.0, max=80000.0,
            mean=59500.0,
        )
    if failure_months is None:
        failure_months = FailureMonthsHistogramDTO(
            histogram=[
                FailureMonthBucketDTO(month=24, count=5),
                FailureMonthBucketDTO(month=36, count=7),
                FailureMonthBucketDTO(month=48, count=3),
            ]
        )
    if max_drawdown is None:
        max_drawdown = MaxDrawdownStatsDTO(
            min=0.02, max=0.35, mean=0.12, median=0.10,
        )
    return ResultStatisticsDTO(
        result_id="r1",
        total_units=total_units,
        success_count=success_count,
        failure_count=failure_count,
        terminal_wealth=terminal_wealth,
        failure_months=failure_months,
        max_drawdown=max_drawdown,
    )


def _make_trajectory(
    months: list[int] | None = None,
    percentiles: list[float] | None = None,
    series: dict[str, list[float]] | None = None,
    total_units: int = 100,
) -> TrajectoryDTO:
    if months is None:
        months = [1, 2, 3, 4, 5, 6]
    if percentiles is None:
        percentiles = [10.0, 50.0, 90.0]
    if series is None:
        series = {
            "p10": [100000, 102000, 104000, 106000, 108000, 110000],
            "p50": [100000, 105000, 110000, 115000, 120000, 125000],
            "p90": [100000, 110000, 120000, 130000, 140000, 150000],
        }
    return TrajectoryDTO(
        result_id="r1",
        total_units=total_units,
        month_count=len(months),
        months=months,
        percentiles=percentiles,
        series=series,
    )


# ===========================================================================
# 1. Wealth Distribution Chart
# ===========================================================================


class TestWealthDistributionChart:
    def test_chart_type_is_bar(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_wealth_distribution_chart(stats)
        assert chart.chart_type == "bar"

    def test_seven_percentile_bars(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_wealth_distribution_chart(stats)
        assert len(chart.labels) == 7
        assert chart.labels == ["Min", "P10", "P25", "Median", "P75", "P90", "Max"]

    def test_dataset_values_match_statistics(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_wealth_distribution_chart(stats)
        assert len(chart.datasets) == 1
        ds = chart.datasets[0]
        assert ds.label == "Terminal Wealth"
        assert ds.data == [45000.0, 48000.0, 52000.0, 60000.0, 68000.0, 72000.0, 80000.0]

    def test_has_reproducibility_envelope(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_wealth_distribution_chart(stats)
        assert chart.reproducibility is not None
        assert chart.reproducibility.execution_mode == "RESULT_SUMMARY"

    def test_custom_title(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_wealth_distribution_chart(stats, title="My Wealth Chart")
        assert chart.title == "My Wealth Chart"

    def test_extreme_values_preserved(self) -> None:
        tw = TerminalWealthStatsDTO(
            min=0.0, p10=100.0, p25=200.0,
            median=500.0, p75=800.0, p90=900.0, max=1000.0,
            mean=500.0,
        )
        stats = _make_statistics(terminal_wealth=tw)
        transformer = ResultVisualizationTransformer()
        chart = transformer.build_wealth_distribution_chart(stats)
        assert chart.datasets[0].data[0] == 0.0
        assert chart.datasets[0].data[-1] == 1000.0


# ===========================================================================
# 2. Failure Timeline Chart
# ===========================================================================


class TestFailureTimelineChart:
    def test_chart_type_is_bar(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_failure_timeline_chart(stats)
        assert chart.chart_type == "bar"

    def test_labels_and_values_from_buckets(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_failure_timeline_chart(stats)
        assert chart.labels == ["Month 24", "Month 36", "Month 48"]
        assert chart.datasets[0].data == [5, 7, 3]

    def test_dataset_label_is_failures(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_failure_timeline_chart(stats)
        assert chart.datasets[0].label == "Failures"

    def test_failure_color_scheme(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_failure_timeline_chart(stats)
        assert chart.datasets[0].border_color == "#ef4444"
        assert "239, 68, 68" in chart.datasets[0].background_color

    def test_no_failures_returns_empty_chart(self) -> None:
        histogram = FailureMonthsHistogramDTO(histogram=[])
        stats = _make_statistics(failure_count=0, failure_months=histogram)
        transformer = ResultVisualizationTransformer()
        chart = transformer.build_failure_timeline_chart(stats)
        assert chart.labels == ["No Failures"]
        assert chart.datasets[0].data == [0]

    def test_single_failure_bucket(self) -> None:
        histogram = FailureMonthsHistogramDTO(
            histogram=[FailureMonthBucketDTO(month=12, count=1)]
        )
        stats = _make_statistics(failure_count=1, failure_months=histogram)
        transformer = ResultVisualizationTransformer()
        chart = transformer.build_failure_timeline_chart(stats)
        assert len(chart.labels) == 1
        assert chart.labels[0] == "Month 12"
        assert chart.datasets[0].data == [1]

    def test_has_reproducibility_envelope(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        chart = transformer.build_failure_timeline_chart(stats)
        assert chart.reproducibility is not None
        assert chart.reproducibility.execution_mode == "RESULT_SUMMARY"


# ===========================================================================
# 3. Trajectory Chart
# ===========================================================================


class TestTrajectoryChart:
    def test_chart_type_is_line(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory()
        chart = transformer.build_trajectory_chart(trajectory)
        assert chart.chart_type == "line"

    def test_one_dataset_per_percentile(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory(percentiles=[10.0, 50.0, 90.0])
        chart = transformer.build_trajectory_chart(trajectory)
        assert len(chart.datasets) == 3

    def test_dataset_labels_match_percentiles(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory(percentiles=[10.0, 25.0, 50.0, 75.0, 90.0])
        chart = transformer.build_trajectory_chart(trajectory)
        labels = [ds.label for ds in chart.datasets]
        assert labels == ["P10", "P25", "P50", "P75", "P90"]

    def test_series_data_passed_through(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory()
        chart = transformer.build_trajectory_chart(trajectory)
        p50 = [ds for ds in chart.datasets if ds.label == "P50"][0]
        assert p50.data == [100000, 105000, 110000, 115000, 120000, 125000]

    def test_month_labels_as_strings(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory(months=[1, 3, 6, 12])
        chart = transformer.build_trajectory_chart(trajectory)
        assert chart.labels == ["1", "3", "6", "12"]

    def test_color_assignment_for_standard_percentiles(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory(percentiles=[10.0, 50.0, 90.0])
        chart = transformer.build_trajectory_chart(trajectory)
        colors = {ds.label: ds.border_color for ds in chart.datasets}
        assert colors["P10"] == "#ef4444"
        assert colors["P50"] == "#38bdf8"
        assert colors["P90"] == "#a855f7"

    def test_custom_percentiles_get_fallback_colors(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory(
            percentiles=[5.0, 15.0, 85.0, 95.0],
            series={
                "p5": [100, 200],
                "p15": [150, 250],
                "p85": [300, 400],
                "p95": [350, 450],
            },
        )
        chart = transformer.build_trajectory_chart(trajectory)
        assert len(chart.datasets) == 4
        for ds in chart.datasets:
            assert ds.border_color is not None

    def test_empty_trajectory(self) -> None:
        trajectory = _make_trajectory(
            months=[], percentiles=[50.0], series={"p50": []},
        )
        transformer = ResultVisualizationTransformer()
        chart = transformer.build_trajectory_chart(trajectory)
        assert chart.labels == []
        assert chart.datasets[0].data == []

    def test_has_reproducibility_envelope(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory()
        chart = transformer.build_trajectory_chart(trajectory)
        assert chart.reproducibility is not None
        assert chart.reproducibility.execution_mode == "RESULT_SUMMARY"

    def test_custom_title(self) -> None:
        transformer = ResultVisualizationTransformer()
        trajectory = _make_trajectory()
        chart = transformer.build_trajectory_chart(trajectory, title="My Trajectory")
        assert chart.title == "My Trajectory"


# ===========================================================================
# 4. Summary Card
# ===========================================================================


class TestSummaryCard:
    def test_card_title(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        card = transformer.build_summary_card(stats)
        assert card.title == "Result Summary"

    def test_custom_title(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        card = transformer.build_summary_card(stats, title="My Card")
        assert card.title == "My Card"

    def test_entry_count(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        card = transformer.build_summary_card(stats)
        assert len(card.entries) == 6

    def test_entry_keys(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        card = transformer.build_summary_card(stats)
        keys = [e.key for e in card.entries]
        assert keys == [
            "total_units", "success_count", "failure_count",
            "median_wealth", "mean_wealth", "max_drawdown_median",
        ]

    def test_total_units_value(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics(total_units=250)
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "total_units"][0]
        assert entry.value == "250"

    def test_success_count_value(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics(success_count=42)
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "success_count"][0]
        assert entry.value == "42"

    def test_failure_count_value(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics(failure_count=7)
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "failure_count"][0]
        assert entry.value == "7"

    def test_median_wealth_formatted(self) -> None:
        tw = TerminalWealthStatsDTO(
            min=1000, p10=2000, p25=3000,
            median=123456.78, p75=5000, p90=6000, max=7000,
            mean=4000,
        )
        stats = _make_statistics(terminal_wealth=tw)
        transformer = ResultVisualizationTransformer()
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "median_wealth"][0]
        assert entry.value == "123,456.78"

    def test_mean_wealth_formatted(self) -> None:
        tw = TerminalWealthStatsDTO(
            min=1000, p10=2000, p25=3000,
            median=4000, p75=5000, p90=6000, max=7000,
            mean=98765.43,
        )
        stats = _make_statistics(terminal_wealth=tw)
        transformer = ResultVisualizationTransformer()
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "mean_wealth"][0]
        assert entry.value == "98,765.43"

    def test_max_drawdown_formatted_as_percentage(self) -> None:
        md = MaxDrawdownStatsDTO(min=0.01, max=0.50, mean=0.20, median=0.15)
        stats = _make_statistics(max_drawdown=md)
        transformer = ResultVisualizationTransformer()
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "max_drawdown_median"][0]
        assert entry.value == "15.00%"

    def test_zero_values(self) -> None:
        tw = TerminalWealthStatsDTO(
            min=0.0, p10=0.0, p25=0.0,
            median=0.0, p75=0.0, p90=0.0, max=0.0,
            mean=0.0,
        )
        md = MaxDrawdownStatsDTO(min=0.0, max=0.0, mean=0.0, median=0.0)
        stats = _make_statistics(
            total_units=0, success_count=0, failure_count=0,
            terminal_wealth=tw, max_drawdown=md,
        )
        transformer = ResultVisualizationTransformer()
        card = transformer.build_summary_card(stats)
        entry = [e for e in card.entries if e.key == "total_units"][0]
        assert entry.value == "0"

    def test_is_summary_card_type(self) -> None:
        transformer = ResultVisualizationTransformer()
        stats = _make_statistics()
        card = transformer.build_summary_card(stats)
        assert isinstance(card, SummaryCardDTO)


# ===========================================================================
# 5. Existing tests (unchanged)
# ===========================================================================


def test_build_empty_cohort_chart() -> None:
    """Verify empty cohort chart specification structure."""
    transformer = ResultVisualizationTransformer()
    chart = transformer.build_empty_cohort_chart("Test Cohort Chart")
    assert chart.chart_type == "heatmap"
    assert chart.title == "Test Cohort Chart"
    assert chart.reproducibility is not None
    assert chart.reproducibility.execution_mode == "DECIMAL_FAST_PATH"


def test_build_swr_curve_chart() -> None:
    """Verify SWR line chart specification structure."""
    transformer = ResultVisualizationTransformer()
    rates = [3.0, 3.5, 4.0]
    successes = [100.0, 98.5, 92.0]
    chart = transformer.build_swr_curve_chart(rates, successes, "SWR Test")
    assert chart.chart_type == "line"
    assert len(chart.datasets) == 1
    assert chart.datasets[0].label == "Success Rate (%)"
    assert len(chart.labels) == 3

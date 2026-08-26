"""Unit tests for visualization models and transformers."""

from __future__ import annotations

from fbf.ui.visualization import ResultVisualizationTransformer


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

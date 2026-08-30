"""Transformers mapping fbf-core execution results to ChartSpecDTO view models."""

from __future__ import annotations

from fbf.core import __version__ as core_version

from fbf.ui import __version__ as ui_version
from fbf.ui.orchestration.persistence_service import (
    ResultStatisticsDTO,
    TrajectoryDTO,
)
from fbf.ui.visualization.models import (
    ChartDatasetDTO,
    ChartSpecDTO,
    ReproducibilityEnvelopeDTO,
    SummaryCardDTO,
    SummaryCardEntryDTO,
)


class ResultVisualizationTransformer:
    """Transforms raw Core execution results into chart specifications."""

    def _make_envelope(self, execution_mode: str) -> ReproducibilityEnvelopeDTO:
        return ReproducibilityEnvelopeDTO(
            core_version=core_version,
            ui_version=ui_version,
            execution_mode=execution_mode,
        )

    def build_empty_cohort_chart(self, title: str = "Cohort Analysis") -> ChartSpecDTO:
        """Construct an initial empty cohort chart specification."""
        return ChartSpecDTO(
            chart_type="heatmap",
            title=title,
            x_axis_label="Start Year",
            y_axis_label="Horizon (Years)",
            labels=[],
            datasets=[],
            reproducibility=self._make_envelope("DECIMAL_FAST_PATH"),
        )

    def build_swr_curve_chart(
        self,
        withdrawal_rates: list[float],
        success_rates: list[float],
        title: str = "Safe Withdrawal Rate Sensitivity",
    ) -> ChartSpecDTO:
        """Transform SWR sweep data into a line chart specification."""
        dataset = ChartDatasetDTO(
            label="Success Rate (%)",
            data=list(zip(withdrawal_rates, success_rates, strict=False)),
            border_color="#38bdf8",
        )
        return ChartSpecDTO(
            chart_type="line",
            title=title,
            x_axis_label="Withdrawal Rate (%)",
            y_axis_label="Success Rate (%)",
            labels=[f"{rate:.2f}%" for rate in withdrawal_rates],
            datasets=[dataset],
            reproducibility=self._make_envelope("OPTIMIZE_SWR"),
        )

    def build_wealth_distribution_chart(
        self,
        statistics: ResultStatisticsDTO,
        title: str = "Terminal Wealth Distribution",
    ) -> ChartSpecDTO:
        """Transform terminal wealth statistics into a bar chart specification.

        Displays the seven percentile statistics (min, p10, p25, median, p75, p90,
        max) as labeled bars.
        """
        tw = statistics.terminal_wealth
        labels = ["Min", "P10", "P25", "Median", "P75", "P90", "Max"]
        values = [tw.min, tw.p10, tw.p25, tw.median, tw.p75, tw.p90, tw.max]
        dataset = ChartDatasetDTO(
            label="Terminal Wealth",
            data=values,
            border_color="#38bdf8",
            background_color="rgba(56, 189, 248, 0.5)",
        )
        return ChartSpecDTO(
            chart_type="bar",
            title=title,
            x_axis_label="Percentile",
            y_axis_label="Terminal Wealth",
            labels=labels,
            datasets=[dataset],
            reproducibility=self._make_envelope("RESULT_SUMMARY"),
        )

    def build_failure_timeline_chart(
        self,
        statistics: ResultStatisticsDTO,
        title: str = "Failure Timeline",
    ) -> ChartSpecDTO:
        """Transform failure-month histogram into a bar chart specification.

        When no failures exist, returns a chart with empty data and an
        appropriate zero-failure label.
        """
        buckets = statistics.failure_months.histogram
        if not buckets:
            return ChartSpecDTO(
                chart_type="bar",
                title=title,
                x_axis_label="Failure Month",
                y_axis_label="Count",
                labels=["No Failures"],
                datasets=[
                    ChartDatasetDTO(
                        label="Failures",
                        data=[0],
                        border_color="#ef4444",
                        background_color="rgba(239, 68, 68, 0.5)",
                    )
                ],
                reproducibility=self._make_envelope("RESULT_SUMMARY"),
            )

        labels = [f"Month {b.month}" for b in buckets]
        values = [b.count for b in buckets]
        dataset = ChartDatasetDTO(
            label="Failures",
            data=values,
            border_color="#ef4444",
            background_color="rgba(239, 68, 68, 0.5)",
        )
        return ChartSpecDTO(
            chart_type="bar",
            title=title,
            x_axis_label="Failure Month",
            y_axis_label="Count",
            labels=labels,
            datasets=[dataset],
            reproducibility=self._make_envelope("RESULT_SUMMARY"),
        )

    def build_trajectory_chart(
        self,
        trajectory: TrajectoryDTO,
        title: str = "Portfolio Trajectory",
    ) -> ChartSpecDTO:
        """Transform percentile-banded trajectory into a multi-line chart.

        Each percentile series (e.g. P10, P25, P50, P75, P90) becomes a
        separate dataset with month labels on the x-axis.
        """
        _COLORS: dict[str, str] = {
            "p10": "#ef4444",
            "p25": "#f97316",
            "p50": "#38bdf8",
            "p75": "#22c55e",
            "p90": "#a855f7",
        }
        _FALLBACK_COLORS = ["#6b7280", "#06b6d4", "#eab308", "#ec4899", "#14b8a6"]

        datasets = []
        for idx, pctl in enumerate(trajectory.percentiles):
            key = f"p{pctl:.0f}"
            color = _COLORS.get(key, _FALLBACK_COLORS[idx % len(_FALLBACK_COLORS)])
            datasets.append(
                ChartDatasetDTO(
                    label=f"P{pctl:.0f}",
                    data=trajectory.series.get(key, []),
                    border_color=color,
                )
            )

        labels = [str(m) for m in trajectory.months]
        return ChartSpecDTO(
            chart_type="line",
            title=title,
            x_axis_label="Month",
            y_axis_label="Portfolio Value",
            labels=labels,
            datasets=datasets,
            reproducibility=self._make_envelope("RESULT_SUMMARY"),
        )

    def build_summary_card(
        self,
        statistics: ResultStatisticsDTO,
        summary: SummaryCardDTO | None = None,
        title: str = "Result Summary",
    ) -> SummaryCardDTO:
        """Transform statistics and summary DTOs into a summary card specification.

        The card displays key aggregate metrics derived directly from the
        pre-computed DTOs.  No calculations are performed — values are
        formatted and mapped into presentation-oriented entries.
        """
        entries = [
            SummaryCardEntryDTO(
                key="total_units",
                label="Total Simulation Units",
                value=str(statistics.total_units),
            ),
            SummaryCardEntryDTO(
                key="success_count",
                label="Successful Runs",
                value=str(statistics.success_count),
            ),
            SummaryCardEntryDTO(
                key="failure_count",
                label="Failed Runs",
                value=str(statistics.failure_count),
            ),
            SummaryCardEntryDTO(
                key="median_wealth",
                label="Median Terminal Wealth",
                value=f"{statistics.terminal_wealth.median:,.2f}",
            ),
            SummaryCardEntryDTO(
                key="mean_wealth",
                label="Mean Terminal Wealth",
                value=f"{statistics.terminal_wealth.mean:,.2f}",
            ),
            SummaryCardEntryDTO(
                key="max_drawdown_median",
                label="Median Max Drawdown",
                value=f"{statistics.max_drawdown.median:.2%}",
            ),
        ]
        return SummaryCardDTO(title=title, entries=entries)

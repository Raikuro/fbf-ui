"""Transformers mapping fbf-core execution results to ChartSpecDTO view models."""

from __future__ import annotations

from fbf.core import __version__ as core_version

from fbf.ui import __version__ as ui_version
from fbf.ui.visualization.models import (
    ChartDatasetDTO,
    ChartSpecDTO,
    ReproducibilityEnvelopeDTO,
)


class ResultVisualizationTransformer:
    """Transforms raw Core execution results into chart specifications."""

    def build_empty_cohort_chart(self, title: str = "Cohort Analysis") -> ChartSpecDTO:
        """Construct an initial empty cohort chart specification."""
        envelope = ReproducibilityEnvelopeDTO(
            core_version=core_version,
            ui_version=ui_version,
            execution_mode="DECIMAL_FAST_PATH",
        )
        return ChartSpecDTO(
            chart_type="heatmap",
            title=title,
            x_axis_label="Start Year",
            y_axis_label="Horizon (Years)",
            labels=[],
            datasets=[],
            reproducibility=envelope,
        )

    def build_swr_curve_chart(
        self,
        withdrawal_rates: list[float],
        success_rates: list[float],
        title: str = "Safe Withdrawal Rate Sensitivity",
    ) -> ChartSpecDTO:
        """Transform SWR sweep data into a line chart specification."""
        envelope = ReproducibilityEnvelopeDTO(
            core_version=core_version,
            ui_version=ui_version,
            execution_mode="OPTIMIZE_SWR",
        )
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
            reproducibility=envelope,
        )

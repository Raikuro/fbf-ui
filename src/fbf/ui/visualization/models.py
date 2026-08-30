"""Visualization view models and chart specification DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReproducibilityEnvelopeDTO(BaseModel):
    """Envelope ensuring backtest reproducibility traceability."""

    core_version: str
    ui_version: str
    study_configuration_hash: str = ""
    dataset_identifier: str = ""
    execution_mode: str = ""
    persistence_mode: str = ""
    execution_timestamp: str = ""


class ChartDatasetDTO(BaseModel):
    """Series dataset within a chart specification."""

    label: str
    data: list[Any]
    background_color: str | None = None
    border_color: str | None = None


class ChartSpecDTO(BaseModel):
    """Framework-agnostic chart specification consumable by frontend renderers."""

    chart_type: str  # e.g., "line", "bar", "heatmap", "scatter"
    title: str
    x_axis_label: str
    y_axis_label: str
    labels: list[str] = Field(default_factory=list)
    datasets: list[ChartDatasetDTO] = Field(default_factory=list)
    reproducibility: ReproducibilityEnvelopeDTO | None = None


class SummaryCardEntryDTO(BaseModel):
    """A single key-value pair in a summary card."""

    key: str
    label: str
    value: str
    unit: str = ""


class SummaryCardDTO(BaseModel):
    """Presentation-oriented summary card specification for the results dashboard."""

    title: str
    entries: list[SummaryCardEntryDTO]

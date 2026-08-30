"""API routes for persistence: browsing stored experiments, plans, and results."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from fbf.ui.config import _DEFAULT_DB_PATH
from fbf.ui.orchestration.persistence_service import (
    ExperimentDetailDTO,
    ExperimentSummaryDTO,
    PersistenceService,
    PlanSummaryDTO,
    ResultStatisticsDTO,
    ResultSummaryDTO,
    TrajectoryDTO,
)

router = APIRouter(prefix="/persistence", tags=["persistence"])
_service = PersistenceService()

_MAX_PERCENTILES = 20
_VALID_PERCENTILE_RANGE = (0.0, 100.0)


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized API error response container."""

    error: ErrorDetail


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    """Construct standardized HTTPException with ErrorResponse detail payload."""
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@router.get(
    "/experiments",
    response_model=list[ExperimentSummaryDTO],
)
def list_experiments() -> list[ExperimentSummaryDTO]:
    """List all experiments with their latest plan status."""
    return _service.list_experiments(_DEFAULT_DB_PATH)


@router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentDetailDTO,
)
def get_experiment(experiment_id: str) -> ExperimentDetailDTO:
    """Get experiment metadata and plan summaries."""
    detail = _service.get_experiment_detail(_DEFAULT_DB_PATH, experiment_id)
    if detail is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "EXPERIMENT_NOT_FOUND",
            f"Experiment {experiment_id!r} not found.",
        )
    return detail


@router.get(
    "/experiments/{experiment_id}/plans",
    response_model=list[PlanSummaryDTO],
)
def list_experiment_plans(experiment_id: str) -> list[PlanSummaryDTO]:
    """List all plans for an experiment."""
    detail = _service.get_experiment_detail(_DEFAULT_DB_PATH, experiment_id)
    if detail is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "EXPERIMENT_NOT_FOUND",
            f"Experiment {experiment_id!r} not found.",
        )
    return detail.plans


@router.get(
    "/plans/{plan_id}/results",
    response_model=ResultSummaryDTO,
)
def get_plan_results(plan_id: str) -> ResultSummaryDTO:
    """Get execution result summary for a plan."""
    summary = _service.get_plan_result_summary(_DEFAULT_DB_PATH, plan_id)
    if summary is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "RESULT_NOT_FOUND",
            f"No execution result found for plan {plan_id!r}.",
        )
    return summary


@router.get(
    "/results/{result_id}/summary",
    response_model=ResultSummaryDTO,
)
def get_result_summary(result_id: str) -> ResultSummaryDTO:
    """Get execution result summary by result_id."""
    summary = _service.get_result_summary_by_id(_DEFAULT_DB_PATH, result_id)
    if summary is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "RESULT_NOT_FOUND",
            f"Execution result {result_id!r} not found.",
        )
    return summary


@router.get(
    "/results/{result_id}/statistics",
    response_model=ResultStatisticsDTO,
)
def get_result_statistics(result_id: str) -> ResultStatisticsDTO:
    """Get aggregated per-unit statistics for an execution result.

    Returns terminal wealth distribution, failure month histogram,
    and max-drawdown statistics computed server-side from persisted data.
    """
    stats = _service.get_result_statistics(_DEFAULT_DB_PATH, result_id)
    if stats is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "RESULT_NOT_FOUND",
            f"Execution result {result_id!r} not found.",
        )
    return stats


def _parse_percentiles(raw: str | None) -> tuple[float, ...]:
    """Parse and validate a comma-separated percentile string.

    Returns a tuple of validated percentile values in [0, 100].
    Raises HTTPException on invalid input.
    """
    if not raw:
        return (10.0, 25.0, 50.0, 75.0, 90.0)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) > _MAX_PERCENTILES:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_PERCENTILES",
            f"Too many percentiles (max {_MAX_PERCENTILES}).",
        )
    values: list[float] = []
    for part in parts:
        try:
            v = float(part)
        except ValueError as exc:
            raise _http_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_PERCENTILES",
                f"Invalid percentile value: {part!r}.",
            ) from exc
        lo, hi = _VALID_PERCENTILE_RANGE
        if v < lo or v > hi:
            raise _http_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_PERCENTILES",
                f"Percentile {v} out of range [{lo}, {hi}].",
            )
        values.append(v)
    return tuple(values)


@router.get(
    "/results/{result_id}/trajectory",
    response_model=TrajectoryDTO,
)
def get_result_trajectory(
    result_id: str,
    percentiles: str | None = Query(
        default=None,
        description="Comma-separated percentile values (0-100). Default: 10,25,50,75,90.",
    ),
) -> TrajectoryDTO:
    """Get percentile-banded trajectory across all simulation units per month.

    Returns portfolio value percentile bands at each month index,
    suitable for rendering median + confidence-interval charts.
    """
    pcts = _parse_percentiles(percentiles)
    traj = _service.get_result_trajectory(_DEFAULT_DB_PATH, result_id, pcts)
    if traj is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND,
            "RESULT_NOT_FOUND",
            f"Execution result {result_id!r} not found.",
        )
    return traj

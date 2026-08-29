"""API routes for persistence: browsing stored experiments, plans, and results."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from fbf.ui.orchestration.persistence_service import (
    ExperimentDetailDTO,
    ExperimentSummaryDTO,
    PersistenceService,
    PlanSummaryDTO,
    ResultSummaryDTO,
)

router = APIRouter(prefix="/persistence", tags=["persistence"])
_service = PersistenceService()

# Default database path — configured at application level, not per-request.
_DEFAULT_DB_PATH = Path("retirement_simulation.db")


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

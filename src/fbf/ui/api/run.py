"""API routes for simulation execution: start, status polling, and cancellation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, status
from fbf.core import build_study_plan
from fbf.core.domain.model.money import Currency, Money
from fbf.core.study.builder import StudyConfiguration
from pydantic import BaseModel, Field

from fbf.ui.orchestration.execution_service import (
    ExecutionService,
    ExecutionStateDTO,
    ExecutionStatus,
)
from fbf.ui.orchestration.study_service import StudyConfigDTO, StudyService

router = APIRouter(prefix="/run", tags=["run"])
_service = ExecutionService()
_study_service = StudyService()


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standardized API error response container."""

    error: ErrorDetail


class ExecuteRequest(BaseModel):
    """Payload for starting a background simulation execution."""

    yaml_content: str = Field(description="Raw YAML study configuration content.")
    data_dir: str | None = Field(
        default=None, description="Optional dataset directory override."
    )
    initial_wealth: str | None = Field(
        default=None,
        description="Initial wealth as decimal string, e.g. '1000000.00'.",
    )


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    """Construct standardized HTTPException with ErrorResponse detail payload."""
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@router.post("/execute", response_model=ExecutionStateDTO, status_code=status.HTTP_201_CREATED)
def start_execution(payload: ExecuteRequest) -> ExecutionStateDTO:
    """Start a background simulation execution from YAML configuration.

    Parses the YAML, builds the study plan synchronously, then submits
    the execution to a background thread pool.  Returns immediately with
    QUEUED status.
    """
    if not payload.yaml_content or not payload.yaml_content.strip():
        raise _http_error(
            status.HTTP_400_BAD_REQUEST, "EMPTY_CONTENT", "YAML content must not be empty."
        )

    wealth = _parse_initial_wealth(payload.initial_wealth)

    try:
        return _service.submit_job(
            yaml_content=payload.yaml_content,
            data_dir=payload.data_dir,
            initial_wealth=wealth,
        )
    except ValueError as err:
        msg = str(err)
        is_schema = any(k in msg for k in ("policy", "cohorts", "dataset"))
        code = "INVALID_SCHEMA" if is_schema else "INVALID_YAML"
        raise _http_error(status.HTTP_400_BAD_REQUEST, code, msg) from None
    except Exception as err:
        import yaml as _yaml_mod

        if isinstance(err, _yaml_mod.YAMLError):
            raise _http_error(
                status.HTTP_400_BAD_REQUEST, "INVALID_YAML", str(err)
            ) from None
        raise


@router.post(
    "/execute-config",
    response_model=ExecutionStateDTO,
    status_code=status.HTTP_201_CREATED,
)
def execute_from_config(payload: StudyConfigDTO) -> ExecutionStateDTO:
    """Start a background simulation execution from structured configuration.

    Converts the StudyConfigDTO to a BuiltStudy via the same path used by
    preview, then submits for background execution.  Returns immediately
    with QUEUED status.
    """
    try:
        canonical = _study_service.config_dto_to_canonical_dict(payload)
        config = StudyConfiguration.from_yaml(canonical)
        default_wealth = Money(Decimal("1000000.00"), Currency.EUR)
        built_study = build_study_plan(
            config, data_dir=None, initial_wealth=default_wealth,
        )
        return _service.submit_built_study(built_study)
    except Exception as err:
        msg = str(err)
        is_schema = any(k in msg for k in ("policy", "cohorts", "dataset"))
        code = "INVALID_SCHEMA" if is_schema else "INVALID_YAML"
        raise _http_error(status.HTTP_400_BAD_REQUEST, code, msg) from None


@router.get("/status/{job_id}", response_model=ExecutionStateDTO)
def get_execution_status(job_id: str) -> ExecutionStateDTO:
    """Get the current status of a simulation execution job."""
    state = _service.get_job_state(job_id)
    if state is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id!r} not found."
        )
    return state


@router.post("/cancel/{job_id}", response_model=ExecutionStateDTO)
def cancel_execution(job_id: str) -> ExecutionStateDTO:
    """Request cancellation of a simulation execution job.

    QUEUED jobs are cancelled immediately.  RUNNING jobs transition to
    CANCELLING; the result is discarded after Core execution completes.
    """
    # Read state before cancellation to detect terminal-state no-op.
    existing = _service.get_job_state(job_id)
    if existing is None:
        raise _http_error(
            status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id!r} not found."
        )

    terminal_states = {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
    if existing.status in terminal_states:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE",
            f"Job is already in terminal state {existing.status.value!r}.",
        )

    state = _service.request_cancel(job_id)
    if state is None:
        # Should not happen — we just checked it exists — but guard anyway.
        raise _http_error(
            status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id!r} not found."
        )

    return state


def _parse_initial_wealth(raw: str | None) -> Money | None:
    """Parse optional initial wealth string into Money."""
    if raw is None:
        return None
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError) as err:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_WEALTH",
            f"Invalid initial_wealth value: {err}",
        ) from None
    return Money(amount, Currency.EUR)

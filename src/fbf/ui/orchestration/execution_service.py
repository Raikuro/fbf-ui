"""Execution state machine and runner orchestration service."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    """Lifecycle states of a simulation or optimization job."""

    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionStateDTO(BaseModel):
    """DTO capturing live execution job state."""

    job_id: str
    status: ExecutionStatus
    progress_percentage: float = 0.0
    units_completed: int = 0
    total_units: int = 0
    error_message: str | None = None
    execution_metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionService:
    """Orchestrates background simulation jobs and state tracking."""

    def __init__(self) -> None:
        self._jobs: dict[str, ExecutionStateDTO] = {}

    def get_job_state(self, job_id: str) -> ExecutionStateDTO | None:
        """Retrieve state for a given execution job ID."""
        return self._jobs.get(job_id)

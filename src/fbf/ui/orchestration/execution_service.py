"""Execution state machine and background runner orchestration service.

Manages simulation job lifecycle with thread-safe state tracking.

Lifecycle::

    QUEUED
      ├── cancel → CANCELLED
      └── start  → RUNNING
                     ├── success → COMPLETED
                     ├── error   → FAILED
                     └── cancel  → CANCELLING → CANCELLED

Cancellation of a RUNNING job is best-effort: Core execution cannot be
interrupted.  The worker transitions through CANCELLING, waits for Core
to return, then discards the result and settles into CANCELLED.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from fbf.core import (
    BuiltStudy,
    ExecutionOptions,
    ResearchExecutionResult,
    build_study_plan,
    execute_study_plan,
)
from fbf.core.domain.model.money import Currency, Money
from fbf.core.persistence import (
    DuplicateStudyError,
    ExperimentIdentity,
    create_persistence_context,
    create_study_repository,
)
from fbf.core.study.builder import StudyConfiguration
from pydantic import BaseModel, Field

from fbf.ui.config import _DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

_DEFAULT_WORKERS = 4
_DEFAULT_INITIAL_WEALTH = Money(Decimal("1000000.00"), Currency.EUR)


class ExecutionStatus(StrEnum):
    """Lifecycle states of a simulation or optimization job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Terminal states — no further transitions possible.
_TERMINAL_STATES: frozenset[ExecutionStatus] = frozenset(
    {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
)


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
    """Orchestrates background simulation jobs and state tracking.

    Thread-safe.  Uses a ThreadPoolExecutor for background execution.
    Call ``shutdown()`` during application teardown.
    """

    def __init__(
        self,
        max_workers: int = _DEFAULT_WORKERS,
        db_path: Path | None = None,
        data_dir: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ExecutionStateDTO] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[ResearchExecutionResult]] = {}
        self._results: dict[str, ResearchExecutionResult] = {}
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._data_dir = data_dir
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="fbf-exec"
        )

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_job_state(self, job_id: str) -> ExecutionStateDTO | None:
        """Retrieve state for a given execution job ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_result(self, job_id: str) -> ResearchExecutionResult | None:
        """Retrieve the execution result for a completed job.

        Returns ``None`` if the job is unknown or has not completed.
        """
        with self._lock:
            return self._results.get(job_id)

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    def submit_job(
        self,
        yaml_content: str,
        data_dir: str | None = None,
        initial_wealth: Money | None = None,
    ) -> ExecutionStateDTO:
        """Parse YAML, build study plan, and submit for background execution.

        Returns the initial QUEUED state.  Raises ``ValueError`` if the YAML
        is invalid or the study plan cannot be built.
        """
        wealth = initial_wealth or _DEFAULT_INITIAL_WEALTH
        config = _parse_and_build_config(yaml_content)
        built_study = build_study_plan(config, data_dir=data_dir, initial_wealth=wealth)
        return self._submit_study(built_study)

    def submit_built_study(self, built_study: BuiltStudy) -> ExecutionStateDTO:
        """Submit a pre-built study plan for background execution.

        Accepts a ``BuiltStudy`` directly, bypassing YAML parsing and plan
        construction.  Returns the initial QUEUED state.
        """
        return self._submit_study(built_study)

    def _submit_study(self, built_study: BuiltStudy) -> ExecutionStateDTO:
        """Submit a BuiltStudy for background execution (shared implementation)."""
        job_id = uuid.uuid4().hex[:12]
        cancel_event = threading.Event()
        state = ExecutionStateDTO(
            job_id=job_id,
            status=ExecutionStatus.QUEUED,
            total_units=len(built_study.plan.units),
        )

        with self._lock:
            self._jobs[job_id] = state
            self._cancel_events[job_id] = cancel_event

        future = self._executor.submit(
            self._run_job, job_id, built_study, cancel_event
        )
        with self._lock:
            self._futures[job_id] = future

        future.add_done_callback(lambda _f: self._cleanup_future(job_id))

        return state

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def request_cancel(self, job_id: str) -> ExecutionStateDTO | None:
        """Request cancellation of a job.

        Returns the updated state, or ``None`` if the job does not exist.

        - QUEUED  → CANCELLED  (worker will skip execution)
        - RUNNING → CANCELLING (worker discards result after Core returns)
        - Terminal states are unchanged (request ignored).
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.status in _TERMINAL_STATES:
                return job  # already done, nothing to cancel

            cancel_event = self._cancel_events.get(job_id)

            if job.status == ExecutionStatus.QUEUED:
                # Worker hasn't started yet — go straight to CANCELLED.
                if cancel_event is not None:
                    cancel_event.set()
                self._jobs[job_id] = job.model_copy(
                    update={"status": ExecutionStatus.CANCELLED}
                )
                return self._jobs[job_id]

            if job.status == ExecutionStatus.RUNNING:
                # Core is executing — transition to CANCELLING.
                if cancel_event is not None:
                    cancel_event.set()
                self._jobs[job_id] = job.model_copy(
                    update={"status": ExecutionStatus.CANCELLING}
                )
                return self._jobs[job_id]

            # CANCELLING — already cancelling, no change.
            return job

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _run_job(
        self,
        job_id: str,
        built_study: BuiltStudy,
        cancel_event: threading.Event,
    ) -> ResearchExecutionResult:
        """Execute a study plan in a background thread.

        Transitions: QUEUED -> RUNNING -> (COMPLETED | FAILED | CANCELLED).

        On success, persists the experiment, plan, and execution result to
        SQLite via Core persistence APIs.  Persistence failure is reported
        as COMPLETED with an error message — the execution itself succeeded.
        """
        # --- Check cancellation before starting ---
        if cancel_event.is_set():
            self._transition(
                job_id,
                ExecutionStatus.CANCELLED,
                error_message="Cancelled before execution started.",
            )
            raise _JobCancelledError("Cancelled before execution started.")

        # --- Transition to RUNNING ---
        self._transition(job_id, ExecutionStatus.RUNNING)

        # --- Build progress callback ---
        progress_callback = self._make_progress_callback(job_id)

        # --- Execute (timed) ---
        try:
            options = ExecutionOptions(progress_callback=progress_callback)
            exec_start = time.perf_counter()
            result = execute_study_plan(built_study, options=options)
            execution_duration = time.perf_counter() - exec_start
        except Exception as exc:
            logger.exception("Job %s failed during execution", job_id)
            self._transition(
                job_id,
                ExecutionStatus.FAILED,
                error_message=str(exc),
            )
            raise

        # --- Check cancellation after Core returns ---
        if cancel_event.is_set():
            self._transition(
                job_id,
                ExecutionStatus.CANCELLED,
                error_message="Execution completed but result was discarded due to cancellation.",
            )
            raise _JobCancelledError("Result discarded due to cancellation.")

        # --- Persist to SQLite ---
        persistence_error: str | None = None
        try:
            self._persist_result(built_study, result, job_id, execution_duration)
        except DuplicateStudyError:
            logger.warning(
                "Job %s: experiment already persisted (idempotent skip)", job_id
            )
        except Exception:
            logger.exception("Job %s: persistence failed", job_id)
            persistence_error = (
                "Execution completed but persistence failed. "
                "Result is available for this session only."
            )

        # --- Store result in memory ---
        with self._lock:
            self._results[job_id] = result

        # --- Transition to COMPLETED ---
        if persistence_error is not None:
            self._transition(
                job_id, ExecutionStatus.COMPLETED, error_message=persistence_error
            )
        else:
            self._transition(job_id, ExecutionStatus.COMPLETED)
        return result

    def _make_progress_callback(self, job_id: str) -> Any:
        """Create a progress callback that updates the job state.

        Only updates when the job is RUNNING.  Ignored during CANCELLING
        or any terminal state.
        """

        def callback(completed: int, total: int) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status != ExecutionStatus.RUNNING:
                    return
                percentage = (completed / total * 100.0) if total > 0 else 0.0
                self._jobs[job_id] = job.model_copy(
                    update={
                        "units_completed": completed,
                        "total_units": total,
                        "progress_percentage": percentage,
                    }
                )

        return callback

    def _persist_result(
        self,
        built_study: BuiltStudy,
        result: ResearchExecutionResult,
        job_id: str,
        execution_duration: float,
    ) -> None:
        """Persist experiment, plan, and execution result to SQLite.

        Uses the existing Core persistence APIs.  Raises on failure so the
        caller can handle persistence errors distinctly from execution errors.
        """
        ctx = create_persistence_context(data_dir=self._data_dir)
        repo = create_study_repository(str(self._db_path))

        identity = ExperimentIdentity(
            name=built_study.experiment_definition.name,
            revision=f"exec-{job_id}",
        )

        experiment_id = repo.save_experiment(
            identity, built_study.experiment_definition, ctx
        )
        plan_id = repo.save_plan(built_study.plan, experiment_id, ctx)
        repo.save_execution_result(plan_id, result, ctx, execution_duration)

    # ------------------------------------------------------------------
    # Internal state transitions
    # ------------------------------------------------------------------

    def _transition(
        self,
        job_id: str,
        new_status: ExecutionStatus,
        error_message: str | None = None,
    ) -> None:
        """Atomically transition a job to a new status."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            updates: dict[str, Any] = {"status": new_status}
            if error_message is not None:
                updates["error_message"] = error_message
            self._jobs[job_id] = job.model_copy(update=updates)

    def _cleanup_future(self, job_id: str) -> None:
        """Remove completed future and cancel event from internal maps."""
        with self._lock:
            self._futures.pop(job_id, None)
            # Keep cancel event and job state for later queries.
            # Events are cleaned up on cancel or could be pruned periodically.

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the background executor.

        Call during application teardown.  Does not cancel running futures.
        """
        self._executor.shutdown(wait=wait)


def _parse_and_build_config(yaml_content: str) -> StudyConfiguration:
    """Parse raw YAML text into a StudyConfiguration via Core."""
    import yaml as _yaml

    if not yaml_content or not yaml_content.strip():
        raise ValueError("YAML content must not be empty.")

    raw_data = _yaml.safe_load(yaml_content)
    if not isinstance(raw_data, dict):
        raise ValueError("Expected YAML mapping at document root.")

    return StudyConfiguration.from_yaml(raw_data)


class _JobCancelledError(Exception):
    """Raised internally when a job is cancelled."""

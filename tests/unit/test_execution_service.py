"""Unit tests for ExecutionService job lifecycle, thread safety, and cancellation."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fbf.ui.orchestration.execution_service import (
    ExecutionService,
    ExecutionStatus,
)

VALID_STUDY_YAML = """
metadata:
  name: Test Study
  description: Test
  version: "1.0"
dataset:
  identifier: sp500_historical
allocation_policy:
  type: ConstantAllocationPolicy
  equity_allocation: [0.60, 0.80]
withdrawal_policy:
  type: FixedRealWithdrawalPolicy
  withdrawal_rate: [0.04]
cohorts:
  horizon_years: [30]
"""


def _make_mock_built_study(total_units: int = 10) -> Any:
    """Create a mock BuiltStudy."""
    built = MagicMock()
    built.plan = MagicMock()
    built.plan.units = [MagicMock() for _ in range(total_units)]
    return built


def _make_mock_result(total_units: int = 10) -> Any:
    """Create a minimal mock ResearchExecutionResult."""
    result = MagicMock()
    result.plan = MagicMock()
    result.plan.units = [MagicMock() for _ in range(total_units)]
    result.experiment_result = MagicMock()
    result.experiment_result.simulation_results = [
        MagicMock() for _ in range(total_units)
    ]
    return result


@pytest.fixture
def service() -> Generator[ExecutionService]:
    """Provide a fresh ExecutionService with controlled threading."""
    svc = ExecutionService(max_workers=2)
    yield svc
    svc.shutdown(wait=True)


# ------------------------------------------------------------------
# State transitions
# ------------------------------------------------------------------


def test_initial_submit_creates_queued_job(service: ExecutionService) -> None:
    """submit_job returns a QUEUED job with correct total_units."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(5),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_make_mock_result(5),
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)

    assert state.status == ExecutionStatus.QUEUED
    assert state.total_units == 5
    assert state.units_completed == 0
    assert state.job_id  # non-empty


def test_get_nonexistent_job_returns_none(service: ExecutionService) -> None:
    """get_job_state returns None for unknown job_id."""
    assert service.get_job_state("nonexistent") is None


def test_job_transitions_to_completed(service: ExecutionService) -> None:
    """A successfully executed job reaches COMPLETED."""
    event = threading.Event()

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.05)
        return _make_mock_result(3)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(3),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=slow_execute,
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        event.wait(timeout=2.0)
        time.sleep(0.2)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.COMPLETED


def test_job_transitions_to_failed_on_exception(service: ExecutionService) -> None:
    """An exception during execution transitions the job to FAILED."""

    def failing_execute(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Core execution exploded")

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(3),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=failing_execute,
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        time.sleep(0.2)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.FAILED
    assert "Core execution exploded" in (final.error_message or "")


# ------------------------------------------------------------------
# Progress callback
# ------------------------------------------------------------------


def test_progress_callback_updates_state(service: ExecutionService) -> None:
    """Progress callback updates units_completed and progress_percentage."""
    callback_captured = threading.Event()
    captured_callback: list[Any] = []

    def capturing_execute(*args: Any, **kwargs: Any) -> Any:
        options = kwargs.get("options")
        if options is not None and options.progress_callback is not None:
            captured_callback.append(options.progress_callback)
        callback_captured.set()
        time.sleep(0.1)
        return _make_mock_result(10)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(10),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=capturing_execute,
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        callback_captured.wait(timeout=2.0)
        # Simulate progress callback invocation from Core thread
        if captured_callback:
            captured_callback[0](5, 10)
        time.sleep(0.15)

    job = service.get_job_state(state.job_id)
    assert job is not None
    assert job.status in (
        ExecutionStatus.RUNNING,
        ExecutionStatus.COMPLETED,
    )


# ------------------------------------------------------------------
# Cancellation — RUNNING jobs
# ------------------------------------------------------------------


def test_cancel_running_job_goes_to_cancelling(service: ExecutionService) -> None:
    """Cancelling a RUNNING job transitions to CANCELLING, then CANCELLED."""
    worker_started = threading.Event()
    worker_block = threading.Event()

    def blocking_execute(*args: Any, **kwargs: Any) -> Any:
        worker_started.set()
        worker_block.wait(timeout=5.0)
        return _make_mock_result(1)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(1),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=blocking_execute,
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        worker_started.wait(timeout=2.0)
        time.sleep(0.05)

        # Confirm RUNNING
        running = service.get_job_state(state.job_id)
        assert running is not None
        assert running.status == ExecutionStatus.RUNNING

        # Cancel
        cancelling = service.request_cancel(state.job_id)
        assert cancelling is not None
        assert cancelling.status == ExecutionStatus.CANCELLING

        # Release worker
        worker_block.set()
        time.sleep(0.3)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.CANCELLED


def test_cancel_running_result_discarded(service: ExecutionService) -> None:
    """After CANCELLING, the worker discards the Core result and reaches CANCELLED."""
    worker_started = threading.Event()
    worker_block = threading.Event()

    def blocking_execute(*args: Any, **kwargs: Any) -> Any:
        worker_started.set()
        worker_block.wait(timeout=5.0)
        return _make_mock_result(1)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(1),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=blocking_execute,
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        worker_started.wait(timeout=2.0)

        service.request_cancel(state.job_id)
        worker_block.set()
        time.sleep(0.3)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.CANCELLED
    assert "discarded" in (final.error_message or "").lower()


# ------------------------------------------------------------------
# Cancellation — terminal states
# ------------------------------------------------------------------


def test_cancel_completed_job_unchanged(service: ExecutionService) -> None:
    """Cancelling a COMPLETED job does not change its state."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(1),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_make_mock_result(1),
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        time.sleep(0.3)

    final_before = service.get_job_state(state.job_id)
    assert final_before is not None
    assert final_before.status == ExecutionStatus.COMPLETED

    result = service.request_cancel(state.job_id)
    assert result is not None
    assert result.status == ExecutionStatus.COMPLETED


def test_cancel_nonexistent_returns_none(service: ExecutionService) -> None:
    """request_cancel returns None for unknown job_id."""
    assert service.request_cancel("nonexistent") is None


# ------------------------------------------------------------------
# Race condition: never COMPLETED after cancellation
# ------------------------------------------------------------------


def test_never_completed_after_cancel(service: ExecutionService) -> None:
    """After cancellation is requested, the job never reaches COMPLETED."""
    worker_started = threading.Event()
    worker_block = threading.Event()

    def blocking_execute(*args: Any, **kwargs: Any) -> Any:
        worker_started.set()
        worker_block.wait(timeout=5.0)
        return _make_mock_result(1)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(1),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=blocking_execute,
        ),
    ):
        state = service.submit_job(VALID_STUDY_YAML)
        worker_started.wait(timeout=2.0)

        service.request_cancel(state.job_id)
        worker_block.set()
        time.sleep(0.3)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status != ExecutionStatus.COMPLETED
    assert final.status == ExecutionStatus.CANCELLED


# ------------------------------------------------------------------
# Concurrent jobs
# ------------------------------------------------------------------


def test_concurrent_jobs_run_independently(service: ExecutionService) -> None:
    """Multiple jobs execute concurrently and reach terminal states."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_make_mock_built_study(2),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_make_mock_result(2),
        ),
    ):
        state1 = service.submit_job(VALID_STUDY_YAML)
        state2 = service.submit_job(VALID_STUDY_YAML)
        state3 = service.submit_job(VALID_STUDY_YAML)
        time.sleep(0.5)

    for s in [state1, state2, state3]:
        final = service.get_job_state(s.job_id)
        assert final is not None
        assert final.status == ExecutionStatus.COMPLETED


# ------------------------------------------------------------------
# Shutdown
# ------------------------------------------------------------------


def test_shutdown_does_not_raise(service: ExecutionService) -> None:
    """shutdown() completes without error."""
    service.shutdown(wait=False)


# ------------------------------------------------------------------
# submit_built_study
# ------------------------------------------------------------------


def test_submit_built_study_creates_queued_job(service: ExecutionService) -> None:
    """submit_built_study returns a QUEUED job with correct total_units."""
    with patch(
        "fbf.ui.orchestration.execution_service.execute_study_plan",
        return_value=_make_mock_result(5),
    ):
        state = service.submit_built_study(_make_mock_built_study(5))

    assert state.status == ExecutionStatus.QUEUED
    assert state.total_units == 5
    assert state.units_completed == 0
    assert state.job_id


def test_submit_built_study_reaches_completed(service: ExecutionService) -> None:
    """A job submitted via submit_built_study reaches COMPLETED."""
    event = threading.Event()

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.05)
        return _make_mock_result(3)

    with patch(
        "fbf.ui.orchestration.execution_service.execute_study_plan",
        side_effect=slow_execute,
    ):
        state = service.submit_built_study(_make_mock_built_study(3))
        event.wait(timeout=2.0)
        time.sleep(0.2)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.COMPLETED


# ------------------------------------------------------------------
# Result storage
# ------------------------------------------------------------------


def test_result_stored_on_completion(service: ExecutionService) -> None:
    """get_result returns the ResearchExecutionResult after COMPLETED."""
    event = threading.Event()
    mock_result = _make_mock_result(3)

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.05)
        return mock_result

    with patch(
        "fbf.ui.orchestration.execution_service.execute_study_plan",
        side_effect=slow_execute,
    ):
        state = service.submit_built_study(_make_mock_built_study(3))
        event.wait(timeout=2.0)
        time.sleep(0.2)

    result = service.get_result(state.job_id)
    assert result is mock_result


def test_result_not_stored_on_failure(service: ExecutionService) -> None:
    """get_result returns None when execution fails."""

    def failing_execute(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Core failed")

    with patch(
        "fbf.ui.orchestration.execution_service.execute_study_plan",
        side_effect=failing_execute,
    ):
        state = service.submit_built_study(_make_mock_built_study(1))
        time.sleep(0.2)

    assert service.get_result(state.job_id) is None


def test_result_not_stored_on_cancellation(service: ExecutionService) -> None:
    """get_result returns None when a running job is cancelled."""
    worker_started = threading.Event()
    worker_block = threading.Event()

    def blocking_execute(*args: Any, **kwargs: Any) -> Any:
        worker_started.set()
        worker_block.wait(timeout=5.0)
        return _make_mock_result(1)

    with patch(
        "fbf.ui.orchestration.execution_service.execute_study_plan",
        side_effect=blocking_execute,
    ):
        state = service.submit_built_study(_make_mock_built_study(1))
        worker_started.wait(timeout=2.0)

        service.request_cancel(state.job_id)
        worker_block.set()
        time.sleep(0.3)

    assert service.get_result(state.job_id) is None
    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.CANCELLED


def test_get_result_nonexistent_returns_none(service: ExecutionService) -> None:
    """get_result returns None for unknown job_id."""
    assert service.get_result("nonexistent") is None

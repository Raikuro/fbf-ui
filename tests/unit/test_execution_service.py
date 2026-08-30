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

_PERSISTENCE_PATCHES = (
    patch(
        "fbf.ui.orchestration.execution_service.create_persistence_context",
    ),
    patch(
        "fbf.ui.orchestration.execution_service.create_study_repository",
    ),
)


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


@pytest.fixture
def _mock_persistence() -> Generator[None]:
    """Mock Core persistence APIs so tests do not touch SQLite."""
    for p in _PERSISTENCE_PATCHES:
        p.start()
    yield
    for p in _PERSISTENCE_PATCHES:
        p.stop()


# ------------------------------------------------------------------
# State transitions
# ------------------------------------------------------------------


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


@pytest.mark.usefixtures("_mock_persistence")
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


# ------------------------------------------------------------------
# P9: Execution result persistence
# ------------------------------------------------------------------


def test_persist_result_calls_core_apis(service: ExecutionService) -> None:
    """_persist_result calls Core persistence APIs with correct arguments."""
    built = _make_mock_built_study(3)
    result = _make_mock_result(3)
    mock_repo = MagicMock()
    mock_repo.save_experiment.return_value = "exp-123"
    mock_repo.save_plan.return_value = "plan-456"

    with (
        patch(
            "fbf.ui.orchestration.execution_service.create_persistence_context"
        ) as mock_ctx,
        patch(
            "fbf.ui.orchestration.execution_service.create_study_repository",
            return_value=mock_repo,
        ),
    ):
        service._persist_result(built, result, "job-abc", 1.23)

    mock_ctx.assert_called_once_with(data_dir=None)
    mock_repo.save_experiment.assert_called_once()
    mock_repo.save_plan.assert_called_once_with(
        built.plan, "exp-123", mock_ctx.return_value
    )
    mock_repo.save_execution_result.assert_called_once_with(
        "plan-456", result, mock_ctx.return_value, 1.23
    )


def test_persist_result_uses_job_id_in_revision(service: ExecutionService) -> None:
    """_persist_result uses exec-{job_id} as the experiment revision."""
    built = _make_mock_built_study(1)
    built.experiment_definition.name = "My Study"
    result = _make_mock_result(1)
    mock_repo = MagicMock()
    mock_repo.save_experiment.return_value = "exp-001"
    mock_repo.save_plan.return_value = "plan-002"

    with (
        patch("fbf.ui.orchestration.execution_service.create_persistence_context"),
        patch(
            "fbf.ui.orchestration.execution_service.create_study_repository",
            return_value=mock_repo,
        ),
    ):
        service._persist_result(built, result, "xyz789", 0.5)

    identity_arg = mock_repo.save_experiment.call_args[0][0]
    assert identity_arg.name == "My Study"
    assert identity_arg.revision == "exec-xyz789"


def test_persist_result_uses_custom_db_path() -> None:
    """_persist_result passes the configured db_path to create_study_repository."""
    from pathlib import Path

    custom_path = Path("/tmp/test_p9.db")
    svc = ExecutionService(max_workers=1, db_path=custom_path)
    built = _make_mock_built_study(1)
    result = _make_mock_result(1)
    mock_repo = MagicMock()
    mock_repo.save_experiment.return_value = "e"
    mock_repo.save_plan.return_value = "p"

    try:
        with (
            patch("fbf.ui.orchestration.execution_service.create_persistence_context"),
            patch(
                "fbf.ui.orchestration.execution_service.create_study_repository",
                return_value=mock_repo,
            ) as mock_factory,
        ):
            svc._persist_result(built, result, "j", 0.1)

        mock_factory.assert_called_once_with(str(custom_path))
    finally:
        svc.shutdown(wait=True)


def test_persist_result_uses_custom_data_dir() -> None:
    """_persist_result passes the configured data_dir to create_persistence_context."""
    svc = ExecutionService(max_workers=1, data_dir="/data/studies")
    built = _make_mock_built_study(1)
    result = _make_mock_result(1)
    mock_repo = MagicMock()
    mock_repo.save_experiment.return_value = "e"
    mock_repo.save_plan.return_value = "p"

    try:
        with (
            patch(
                "fbf.ui.orchestration.execution_service.create_persistence_context"
            ) as mock_ctx,
            patch(
                "fbf.ui.orchestration.execution_service.create_study_repository",
                return_value=mock_repo,
            ),
        ):
            svc._persist_result(built, result, "j", 0.1)

        mock_ctx.assert_called_once_with(data_dir="/data/studies")
    finally:
        svc.shutdown(wait=True)


@pytest.mark.usefixtures("_mock_persistence")
def test_job_completed_with_persistence_success(service: ExecutionService) -> None:
    """A successful execution with successful persistence reaches COMPLETED without error."""
    event = threading.Event()

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.05)
        return _make_mock_result(2)

    with patch(
        "fbf.ui.orchestration.execution_service.execute_study_plan",
        side_effect=slow_execute,
    ):
        state = service.submit_built_study(_make_mock_built_study(2))
        event.wait(timeout=2.0)
        time.sleep(0.3)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.COMPLETED
    assert final.error_message is None


@pytest.mark.usefixtures("_mock_persistence")
def test_job_completed_with_persistence_failure(service: ExecutionService) -> None:
    """A successful execution with failed persistence reaches COMPLETED with error message."""

    def failing_persist(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("SQLite disk full")

    event = threading.Event()

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.05)
        return _make_mock_result(2)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=slow_execute,
        ),
        patch.object(
            ExecutionService, "_persist_result", side_effect=failing_persist
        ),
    ):
        state = service.submit_built_study(_make_mock_built_study(2))
        event.wait(timeout=2.0)
        time.sleep(0.3)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.COMPLETED
    assert final.error_message is not None
    assert "persistence failed" in final.error_message.lower()


@pytest.mark.usefixtures("_mock_persistence")
def test_job_completed_with_duplicate_study_error(service: ExecutionService) -> None:
    """A successful execution with DuplicateStudyError reaches COMPLETED without error."""
    from fbf.core.persistence import DuplicateStudyError

    def duplicate_persist(*args: Any, **kwargs: Any) -> Any:
        raise DuplicateStudyError("Study already exists")

    event = threading.Event()

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.05)
        return _make_mock_result(2)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=slow_execute,
        ),
        patch.object(
            ExecutionService, "_persist_result", side_effect=duplicate_persist
        ),
    ):
        state = service.submit_built_study(_make_mock_built_study(2))
        event.wait(timeout=2.0)
        time.sleep(0.3)

    final = service.get_job_state(state.job_id)
    assert final is not None
    assert final.status == ExecutionStatus.COMPLETED
    assert final.error_message is None


@pytest.mark.usefixtures("_mock_persistence")
def test_execution_duration_excludes_persistence(service: ExecutionService) -> None:
    """duration_seconds passed to save_execution_result excludes persistence time."""
    event = threading.Event()
    persist_captured: list[float] = []

    def slow_execute(*args: Any, **kwargs: Any) -> Any:
        event.set()
        time.sleep(0.1)
        return _make_mock_result(1)

    def capture_duration(
        _built: Any, _result: Any, _job_id: str, duration: float
    ) -> None:
        persist_captured.append(duration)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=slow_execute,
        ),
        patch.object(
            ExecutionService, "_persist_result", side_effect=capture_duration
        ),
    ):
        service.submit_built_study(_make_mock_built_study(1))
        event.wait(timeout=2.0)
        time.sleep(0.3)

    assert len(persist_captured) == 1
    assert persist_captured[0] >= 0.05
    assert persist_captured[0] < 1.0

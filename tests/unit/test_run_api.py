"""Unit tests for simulation execution API endpoints."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fbf.ui.main import create_app
from fbf.ui.orchestration.execution_service import ExecutionService, ExecutionStatus

VALID_STUDY_YAML = """
metadata:
  name: Baseline Study
  description: Test backtest study configuration
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

MALFORMED_YAML = """
metadata: [invalid yaml structure : : :
"""

INVALID_SCHEMA_YAML = """
metadata:
  name: Incomplete Study
dataset:
  identifier: sp500_historical
"""


def _mock_built_study(total_units: int = 5) -> Any:
    """Create a mock BuiltStudy."""
    built = MagicMock()
    built.plan = MagicMock()
    built.plan.units = [MagicMock() for _ in range(total_units)]
    return built


def _mock_result(total_units: int = 5) -> Any:
    """Create a mock ResearchExecutionResult."""
    result = MagicMock()
    result.plan = MagicMock()
    result.plan.units = [MagicMock() for _ in range(total_units)]
    result.experiment_result = MagicMock()
    result.experiment_result.simulation_results = [
        MagicMock() for _ in range(total_units)
    ]
    return result


@pytest.fixture
def client() -> Generator[TestClient]:
    """Provide a TestClient with a fresh ExecutionService and no lifespan shutdown."""
    fresh_service = ExecutionService(max_workers=2)
    with (
        patch("fbf.ui.api.run._service", fresh_service),
        patch("fbf.ui.main._execution_service", fresh_service),
    ):
        app = create_app()
        with TestClient(app) as test_client:
            yield test_client
    fresh_service.shutdown(wait=True)


def test_execute_valid_yaml(client: TestClient) -> None:
    """POST /api/v1/run/execute with valid YAML returns 201 with QUEUED status."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_mock_built_study(5),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_mock_result(5),
        ),
    ):
        response = client.post(
            "/api/v1/run/execute",
            json={"yaml_content": VALID_STUDY_YAML},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "QUEUED"
    assert data["job_id"]
    assert data["total_units"] == 5
    assert data["units_completed"] == 0


def test_execute_empty_yaml(client: TestClient) -> None:
    """POST /api/v1/run/execute with empty YAML returns 400."""
    response = client.post(
        "/api/v1/run/execute",
        json={"yaml_content": "   "},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "EMPTY_CONTENT"


def test_execute_malformed_yaml(client: TestClient) -> None:
    """POST /api/v1/run/execute with malformed YAML returns 400."""
    response = client.post(
        "/api/v1/run/execute",
        json={"yaml_content": MALFORMED_YAML},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] in ("INVALID_YAML", "INVALID_SCHEMA")


def test_execute_invalid_schema(client: TestClient) -> None:
    """POST /api/v1/run/execute with missing schema fields returns 400."""
    response = client.post(
        "/api/v1/run/execute",
        json={"yaml_content": INVALID_SCHEMA_YAML},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_SCHEMA"


def test_status_found(client: TestClient) -> None:
    """GET /api/v1/run/status/{job_id} returns 200 with job state."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_mock_built_study(3),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_mock_result(3),
        ),
    ):
        exec_resp = client.post(
            "/api/v1/run/execute",
            json={"yaml_content": VALID_STUDY_YAML},
        )
        assert exec_resp.status_code == 201
        job_id = exec_resp.json()["job_id"]

        time.sleep(0.3)

        response = client.get(f"/api/v1/run/status/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] in {s.value for s in ExecutionStatus}


def test_status_not_found(client: TestClient) -> None:
    """GET /api/v1/run/status/{job_id} returns 404 for unknown job."""
    response = client.get("/api/v1/run/status/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "JOB_NOT_FOUND"


def test_cancel_found(client: TestClient) -> None:
    """POST /api/v1/run/cancel/{job_id} cancels a RUNNING job."""
    worker_started = threading.Event()
    worker_block = threading.Event()

    def blocking_execute(*args: Any, **kwargs: Any) -> Any:
        worker_started.set()
        worker_block.wait(timeout=5.0)
        return _mock_result(1)

    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_mock_built_study(1),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            side_effect=blocking_execute,
        ),
    ):
        exec_resp = client.post(
            "/api/v1/run/execute",
            json={"yaml_content": VALID_STUDY_YAML},
        )
        assert exec_resp.status_code == 201
        job_id = exec_resp.json()["job_id"]

        worker_started.wait(timeout=2.0)
        time.sleep(0.05)

        response = client.post(f"/api/v1/run/cancel/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ExecutionStatus.CANCELLING.value

        worker_block.set()
        time.sleep(0.3)


def test_cancel_not_found(client: TestClient) -> None:
    """POST /api/v1/run/cancel/{job_id} returns 404 for unknown job."""
    response = client.post("/api/v1/run/cancel/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "JOB_NOT_FOUND"


def test_cancel_terminal_state(client: TestClient) -> None:
    """POST /api/v1/run/cancel/{job_id} returns 409 for completed job."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_mock_built_study(1),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_mock_result(1),
        ),
    ):
        exec_resp = client.post(
            "/api/v1/run/execute",
            json={"yaml_content": VALID_STUDY_YAML},
        )
        job_id = exec_resp.json()["job_id"]
        time.sleep(0.3)

        response = client.post(f"/api/v1/run/cancel/{job_id}")
        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["error"]["code"] == "INVALID_STATE"


def test_execute_then_status_flow(client: TestClient) -> None:
    """Full lifecycle: execute -> poll -> completed."""
    with (
        patch(
            "fbf.ui.orchestration.execution_service.build_study_plan",
            return_value=_mock_built_study(3),
        ),
        patch(
            "fbf.ui.orchestration.execution_service.execute_study_plan",
            return_value=_mock_result(3),
        ),
    ):
        exec_resp = client.post(
            "/api/v1/run/execute",
            json={"yaml_content": VALID_STUDY_YAML},
        )
        assert exec_resp.status_code == 201
        job_id = exec_resp.json()["job_id"]
        assert exec_resp.json()["status"] == "QUEUED"

        for _ in range(20):
            time.sleep(0.1)
            status_resp = client.get(f"/api/v1/run/status/{job_id}")
            assert status_resp.status_code == 200
            if status_resp.json()["status"] == "COMPLETED":
                break

        final = client.get(f"/api/v1/run/status/{job_id}").json()
        assert final["status"] == "COMPLETED"

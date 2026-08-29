"""Tests for study plan preview API endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from fbf.ui.orchestration.study_service import ParameterAxisDTO, StudyPlanPreviewDTO


@pytest.fixture
def valid_preview_dto() -> StudyPlanPreviewDTO:
    """Provide a valid preview DTO for testing."""
    return StudyPlanPreviewDTO(
        study_name="Test Study",
        description="A test study",
        version="1.0",
        dataset_identifier="test_dataset",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_values=[0.6],
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_values=[0.04],
        horizon_years=[30],
        num_cohorts=100,
        num_parameter_configs=3,
        total_simulation_units=300,
        cohort_date_start="1970-01-01",
        cohort_date_end="2000-12-01",
        parameter_axes=[
            ParameterAxisDTO(name="equity_allocation", values=[0.6]),
            ParameterAxisDTO(name="withdrawal_rate", values=[0.04]),
            ParameterAxisDTO(name="horizon_years", values=[30.0]),
        ],
        experiment_horizon_months=361,
        initial_wealth="1000000.00",
    )


class TestStudyPlanPreviewAPI:
    """Test study plan preview API endpoint."""

    def test_preview_endpoint_returns_200(
        self, client: Any, valid_preview_dto: StudyPlanPreviewDTO
    ) -> None:
        """Test that preview endpoint returns 200 with valid configuration."""
        payload = {
            "name": "Test Study",
            "description": "A test study",
            "version": "1.0",
            "dataset_identifier": "test_dataset",
            "allocation_policy_type": "ConstantAllocationPolicy",
            "allocation_policy_values": [0.6],
            "withdrawal_policy_type": "FixedRealWithdrawalPolicy",
            "withdrawal_policy_values": [0.04],
            "horizon_years": [30],
        }

        with patch("fbf.ui.api.study._service.preview_study_plan") as mock_preview:
            mock_preview.return_value = valid_preview_dto
            response = client.post("/api/v1/study/preview", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["study_name"] == "Test Study"
            assert data["num_cohorts"] == 100
            assert data["num_parameter_configs"] == 3
            assert data["total_simulation_units"] == 300

    def test_preview_endpoint_returns_400_on_error(self, client: Any) -> None:
        """Test that preview endpoint returns 400 when plan building fails."""
        payload = {
            "name": "Test Study",
            "dataset_identifier": "",
            "allocation_policy_type": "ConstantAllocationPolicy",
            "allocation_policy_values": [0.6],
            "withdrawal_policy_type": "FixedRealWithdrawalPolicy",
            "withdrawal_policy_values": [0.04],
            "horizon_years": [30],
        }

        with patch("fbf.ui.api.study._service.preview_study_plan") as mock_preview:
            mock_preview.side_effect = ValueError("Dataset not found")
            response = client.post("/api/v1/study/preview", json=payload)

            assert response.status_code == 400
            data = response.json()
            assert "detail" in data
            assert data["detail"]["error"]["code"] == "PLAN_BUILD_FAILED"

    def test_preview_endpoint_structure(
        self, client: Any, valid_preview_dto: StudyPlanPreviewDTO
    ) -> None:
        """Test that preview endpoint returns correct structure."""
        payload = {
            "name": "Test Study",
            "dataset_identifier": "test_dataset",
            "allocation_policy_type": "ConstantAllocationPolicy",
            "allocation_policy_values": [0.6, 0.7],
            "withdrawal_policy_type": "FixedRealWithdrawalPolicy",
            "withdrawal_policy_values": [0.04, 0.05],
            "horizon_years": [30, 40],
        }

        with patch("fbf.ui.api.study._service.preview_study_plan") as mock_preview:
            mock_preview.return_value = StudyPlanPreviewDTO(
                study_name="Test Study",
                description="",
                version="",
                dataset_identifier="test_dataset",
                allocation_policy_type="ConstantAllocationPolicy",
                allocation_values=[0.6, 0.7],
                withdrawal_policy_type="FixedRealWithdrawalPolicy",
                withdrawal_values=[0.04, 0.05],
                horizon_years=[30, 40],
                num_cohorts=100,
                num_parameter_configs=8,
                total_simulation_units=800,
                cohort_date_start="1970-01-01",
                cohort_date_end="2000-12-01",
                parameter_axes=[
                    ParameterAxisDTO(name="equity_allocation", values=[0.6, 0.7]),
                    ParameterAxisDTO(name="withdrawal_rate", values=[0.04, 0.05]),
                    ParameterAxisDTO(name="horizon_years", values=[30.0, 40.0]),
                ],
                experiment_horizon_months=481,
                initial_wealth="1000000.00",
            )
            response = client.post("/api/v1/study/preview", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert len(data["allocation_values"]) == 2
            assert len(data["withdrawal_values"]) == 2
            assert len(data["horizon_years"]) == 2
            assert len(data["parameter_axes"]) == 3
            assert data["num_parameter_configs"] == 8
            assert data["total_simulation_units"] == 800

    def test_preview_endpoint_with_optional_targets(
        self, client: Any
    ) -> None:
        """Test preview endpoint with optional final_value_target_values."""
        payload = {
            "name": "Test Study",
            "dataset_identifier": "test_dataset",
            "allocation_policy_type": "ConstantAllocationPolicy",
            "allocation_policy_values": [0.6],
            "withdrawal_policy_type": "FixedRealWithdrawalPolicy",
            "withdrawal_policy_values": [0.04],
            "horizon_years": [30],
            "final_value_target_values": [100000.0, 200000.0],
        }

        with patch("fbf.ui.api.study._service.preview_study_plan") as mock_preview:
            mock_preview.return_value = StudyPlanPreviewDTO(
                study_name="Test Study",
                description="",
                version="",
                dataset_identifier="test_dataset",
                allocation_policy_type="ConstantAllocationPolicy",
                allocation_values=[0.6],
                withdrawal_policy_type="FixedRealWithdrawalPolicy",
                withdrawal_values=[0.04],
                horizon_years=[30],
                final_value_target_values=[100000.0, 200000.0],
                num_cohorts=100,
                num_parameter_configs=2,
                total_simulation_units=200,
                cohort_date_start="1970-01-01",
                cohort_date_end="2000-12-01",
                parameter_axes=[
                    ParameterAxisDTO(name="equity_allocation", values=[0.6]),
                    ParameterAxisDTO(name="withdrawal_rate", values=[0.04]),
                    ParameterAxisDTO(name="horizon_years", values=[30.0]),
                    ParameterAxisDTO(name="final_value_target", values=[100000.0, 200000.0]),
                ],
                experiment_horizon_months=361,
                initial_wealth="1000000.00",
            )
            response = client.post("/api/v1/study/preview", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["final_value_target_values"] == [100000.0, 200000.0]
            assert len(data["parameter_axes"]) == 4

    def test_preview_endpoint_empty_body(self, client: Any) -> None:
        """Test preview endpoint with empty body returns 400 due to missing required fields."""
        response = client.post("/api/v1/study/preview", json={})

        assert response.status_code == 400

    def test_preview_endpoint_invalid_payload(self, client: Any) -> None:
        """Test preview endpoint with invalid payload type."""
        response = client.post("/api/v1/study/preview", json="not a dict")

        assert response.status_code == 422

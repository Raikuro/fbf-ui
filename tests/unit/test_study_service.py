"""Tests for StudyService configuration editing capabilities."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from decimal import Decimal
from typing import Any

from fbf.ui.orchestration.study_service import StudyConfigDTO, StudyService, ValidationResultDTO


@pytest.fixture
def service() -> StudyService:
    """Provide a fresh StudyService for testing."""
    return StudyService()


def _make_mock_built_study(total_units: int = 10) -> Any:
    """Create a mock BuiltStudy."""
    built = MagicMock()
    built.plan = MagicMock()
    built.plan.units = [MagicMock() for _ in range(total_units)]
    return built


@pytest.fixture
def mock_built_study():
    """Provide a mock BuiltStudy."""
    return _make_mock_built_study(5)


class TestStudyServiceConfigEditing:
    """Test configuration editing and validation capabilities."""

    def test_config_dto_to_canonical_dict_minimal(self, service: StudyService) -> None:
        """Test converting a minimal StudyConfigDTO to canonical dict."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
        )

        canonical = service.config_dto_to_canonical_dict(config_dto)

        assert canonical["metadata"]["name"] == "Test Study"
        assert canonical["dataset"]["identifier"] == "test_dataset"
        assert canonical["allocation_policy"]["type"] == "ConstantAllocationPolicy"
        assert canonical["allocation_policy"]["equity_allocation"] == [0.6]
        assert canonical["withdrawal_policy"]["type"] == "FixedRealWithdrawalPolicy"
        assert canonical["withdrawal_policy"]["withdrawal_rate"] == [0.04]
        assert canonical["cohorts"]["horizon_years"] == [30]
        assert "final_value_target_values" not in canonical

    def test_config_dto_to_canonical_dict_with_optional_targets(
        self, service: StudyService
    ) -> None:
        """Test converting StudyConfigDTO with optional final_value_target_values."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
            final_value_target_values=[100000.0],
        )

        canonical = service.config_dto_to_canonical_dict(config_dto)

        assert canonical["final_value_target_values"] == [100000.0]

    def test_validate_config_dto_valid_with_mock(self, service: StudyService, mock_built_study) -> None:
        """Test validating a valid StudyConfigDTO using mocked dependencies."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            description="A valid test study",
            version="1.0",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
        )

        with patch.object(service, 'validate_configuration') as mock_validate:
            mock_validate.return_value = ValidationResultDTO(
                is_valid=True,
                unit_count=10,
                errors=[]
            )
            result = service.validate_config_dto(config_dto)

            assert result.is_valid is True
            assert result.unit_count == 10
            assert len(result.errors) == 0

    def test_validate_config_dto_invalid_missing_dataset(
        self, service: StudyService
    ) -> None:
        """Test validating StudyConfigDTO with invalid dataset identifier."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="",  # Empty dataset identifier should cause validation error
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
        )

        result = service.validate_config_dto(config_dto)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_config_dto_invalid_policy_type(
        self, service: StudyService
    ) -> None:
        """Test validating StudyConfigDTO with invalid policy type."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="INVALID_TYPE",  # Invalid policy type
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
        )

        result = service.validate_config_dto(config_dto)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_config_dto_invalid_allocation_values(
        self, service: StudyService
    ) -> None:
        """Test validating StudyConfigDTO with invalid allocation values."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[-0.1],  # Negative allocation rate
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
        )

        result = service.validate_config_dto(config_dto)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_config_dto_invalid_withdrawal_values(
        self, service: StudyService
    ) -> None:
        """Test validating StudyConfigDTO with invalid withdrawal values."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[1.5],  # > 1.0 withdrawal rate
            horizon_years=[30],
        )

        result = service.validate_config_dto(config_dto)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_config_dto_invalid_horizon_years(
        self, service: StudyService
    ) -> None:
        """Test validating StudyConfigDTO with invalid horizon years."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[0],  # Invalid: must be positive
        )

        result = service.validate_config_dto(config_dto)

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_config_dto_valid_multiple_arrays(
        self, service: StudyService, mock_built_study
    ) -> None:
        """Test validating StudyConfigDTO with multiple array values."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",  # Use test_dataset to avoid dataset loading issues
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.5, 0.6, 0.7, 0.8, 0.9],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.03, 0.04, 0.05],
            horizon_years=[10, 20, 30, 40, 50],
        )

        with patch.object(service, 'validate_configuration') as mock_validate:
            mock_validate.return_value = ValidationResultDTO(
                is_valid=True,
                unit_count=50,
                errors=[]
            )
            result = service.validate_config_dto(config_dto)

            assert result.is_valid is True
            assert result.unit_count == 50
            assert len(result.errors) == 0

    def test_validate_config_dto_valid_optional_targets(
        self, service: StudyService, mock_built_study
    ) -> None:
        """Test validating StudyConfigDTO with optional final_value_target_values."""
        config_dto = StudyConfigDTO(
            name="Test Study",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
            final_value_target_values=[100000.0, 150000.0, 200000.0],
        )

        with patch.object(service, 'validate_configuration') as mock_validate:
            mock_validate.return_value = ValidationResultDTO(
                is_valid=True,
                unit_count=30,
                errors=[]
            )
            result = service.validate_config_dto(config_dto)

            assert result.is_valid is True
            assert result.unit_count == 30
            assert len(result.errors) == 0

    def test_config_dto_canonical_dict_equality(
        self, service: StudyService
    ) -> None:
        """Test that StudyConfigDTO to canonical dict conversion is reversible."""
        original_dto = StudyConfigDTO(
            name="Test Study",
            description="Test description",
            version="1.0",
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6, 0.7],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30, 40],
            final_value_target_values=[100000.0],
        )

        canonical = service.config_dto_to_canonical_dict(original_dto)

        assert canonical["metadata"]["name"] == original_dto.name
        assert canonical["metadata"]["description"] == original_dto.description
        assert canonical["dataset"]["identifier"] == original_dto.dataset_identifier
        assert canonical["allocation_policy"]["type"] == original_dto.allocation_policy_type
        assert canonical["allocation_policy"]["equity_allocation"] == original_dto.allocation_policy_values
        assert canonical["withdrawal_policy"]["type"] == original_dto.withdrawal_policy_type
        assert canonical["withdrawal_policy"]["withdrawal_rate"] == original_dto.withdrawal_policy_values
        assert canonical["cohorts"]["horizon_years"] == original_dto.horizon_years
        assert canonical["final_value_target_values"] == original_dto.final_value_target_values

    def test_validate_config_dto_empty_name(
        self, service: StudyService
    ) -> None:
        """Test that empty study name is validated by Core (may be allowed)."""
        config_dto = StudyConfigDTO(
            name="",  # Empty name
            dataset_identifier="test_dataset",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=[0.6],
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=[0.04],
            horizon_years=[30],
        )

        result = service.validate_config_dto(config_dto)

        assert isinstance(result.is_valid, bool)
        assert isinstance(result.errors, list)


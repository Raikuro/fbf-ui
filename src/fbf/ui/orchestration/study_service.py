"""Study configuration, parsing, and validation orchestration service."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.domain.model.money import Currency, Money
from fbf.core.study.builder import StudyConfiguration, build_study_plan, load_yaml
from pydantic import BaseModel, Field


class PathForbiddenError(Exception):
    """Raised when a requested path is outside the allowed workspace root."""


class StudyConfigDTO(BaseModel):
    """Decoupled DTO representing canonical StudyConfiguration for the UI API."""

    name: str = Field(default="Unnamed Study")
    description: str = Field(default="")
    version: str = Field(default="")
    dataset_identifier: str = Field(default="")
    allocation_policy_type: str = Field(default="")
    allocation_policy_values: list[float] = Field(default_factory=list)
    withdrawal_policy_type: str = Field(default="")
    withdrawal_policy_values: list[float] = Field(default_factory=list)
    horizon_years: list[int] = Field(default_factory=list)
    final_value_target_values: list[float] | None = None


class ValidationResultDTO(BaseModel):
    """DTO capturing study plan validation outcomes."""

    is_valid: bool
    unit_count: int = 0
    errors: list[str] = Field(default_factory=list)


def study_configuration_to_dto(config: StudyConfiguration) -> StudyConfigDTO:
    """Convert canonical fbf-core StudyConfiguration into StudyConfigDTO."""
    targets = (
        [float(v) for v in config.final_value_target_values]
        if config.final_value_target_values is not None
        else None
    )
    return StudyConfigDTO(
        name=config.name,
        description=config.description,
        version=config.version,
        dataset_identifier=config.dataset_identifier,
        allocation_policy_type=config.allocation_policy_type,
        allocation_policy_values=[float(v) for v in config.allocation_policy_values],
        withdrawal_policy_type=config.withdrawal_policy_type,
        withdrawal_policy_values=[float(v) for v in config.withdrawal_policy_values],
        horizon_years=list(config.horizon_years),
        final_value_target_values=targets,
    )


class StudyService:
    """Orchestrates study parsing, DTO adaptation, and plan validation."""

    MAX_UPLOAD_BYTES: int = 2 * 1024 * 1024  # 2 MB limit

    def __init__(self, workspace_root: Path | None = None) -> None:
        self._workspace_root = (workspace_root or Path.cwd()).resolve()

    @property
    def workspace_root(self) -> Path:
        """Return resolved allowed workspace root path."""
        return self._workspace_root

    def parse_yaml_text(self, raw_text: str) -> StudyConfigDTO:
        """Parse raw YAML text payload into StudyConfigDTO via Core."""
        try:
            import yaml
        except ImportError as err:
            raise RuntimeError("PyYAML is required for YAML parsing.") from err

        if not raw_text or not raw_text.strip():
            raise ValueError("YAML content must not be empty.")

        raw_data = yaml.safe_load(raw_text)
        if not isinstance(raw_data, dict):
            raise ValueError("Expected YAML mapping at document root.")

        config = StudyConfiguration.from_yaml(raw_data)
        return study_configuration_to_dto(config)

    def resolve_permitted_path(self, target_path: str | Path) -> Path:
        """Resolve target path and verify it stays within allowed workspace root."""
        path_obj = Path(target_path)
        if not path_obj.is_absolute():
            resolved = (self._workspace_root / path_obj).resolve()
        else:
            resolved = path_obj.resolve()

        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            raise PathForbiddenError(
                "Access denied: path is outside permitted workspace root."
            ) from None

        return resolved

    def parse_server_file(self, target_path: str | Path) -> StudyConfigDTO:
        """Parse a server filesystem file into StudyConfigDTO following workspace path security."""
        resolved = self.resolve_permitted_path(target_path)

        if not resolved.exists():
            raise FileNotFoundError(f"File not found at path: {resolved.name}")
        if resolved.is_dir():
            raise IsADirectoryError(f"Requested path is a directory: {resolved.name}")

        raw_data = load_yaml(resolved)
        config = StudyConfiguration.from_yaml(raw_data)
        return study_configuration_to_dto(config)

    def validate_configuration(
        self, raw_config: dict[str, Any], data_dir: str | None = None
    ) -> ValidationResultDTO:
        """Validate raw dictionary config by attempting to build a study plan."""
        try:
            config = StudyConfiguration.from_yaml(raw_config)
            initial_wealth = Money(Decimal("1000000.00"), Currency.EUR)
            built_study = build_study_plan(
                config, data_dir=data_dir, initial_wealth=initial_wealth
            )
            return ValidationResultDTO(
                is_valid=True,
                unit_count=len(built_study.plan.units),
                errors=[],
            )
        except Exception as err:
            return ValidationResultDTO(
                is_valid=False,
                unit_count=0,
                errors=[str(err)],
            )

    def config_dto_to_canonical_dict(self, config_dto: StudyConfigDTO) -> dict[str, Any]:
        """Convert StudyConfigDTO back to canonical Core configuration dict."""
        canonical = {
            "metadata": {
                "name": config_dto.name,
                "description": config_dto.description,
                "version": config_dto.version,
            },
            "dataset": {
                "identifier": config_dto.dataset_identifier,
            },
            "allocation_policy": {
                "type": config_dto.allocation_policy_type,
                "equity_allocation": config_dto.allocation_policy_values,
            },
            "withdrawal_policy": {
                "type": config_dto.withdrawal_policy_type,
                "withdrawal_rate": config_dto.withdrawal_policy_values,
            },
            "cohorts": {
                "horizon_years": config_dto.horizon_years,
            },
        }

        if config_dto.final_value_target_values is not None:
            canonical["final_value_target_values"] = config_dto.final_value_target_values

        return canonical

    def validate_config_dto(
        self, config_dto: StudyConfigDTO, data_dir: str | None = None
    ) -> ValidationResultDTO:
        """Validate StudyConfigDTO fields using Core validation."""
        canonical = self.config_dto_to_canonical_dict(config_dto)
        return self.validate_configuration(canonical, data_dir)

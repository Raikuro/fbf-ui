"""Study configuration and validation orchestration service."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.domain.model.money import Currency, Money
from fbf.core.study.builder import StudyConfiguration, build_study_plan, load_yaml
from pydantic import BaseModel, Field


class StudyConfigDTO(BaseModel):
    """Decoupled DTO representing study configuration parameters for the UI API."""

    study_name: str = Field(default="Unnamed Study")
    raw_data: dict[str, Any] = Field(default_factory=dict)


class ValidationResultDTO(BaseModel):
    """DTO capturing study plan validation outcomes."""

    is_valid: bool
    unit_count: int = 0
    errors: list[str] = Field(default_factory=list)


class StudyService:
    """Orchestrates study parsing, DTO adaptation, and plan validation."""

    def parse_yaml_file(self, path: Path) -> dict[str, Any]:
        """Parse raw YAML mapping using Core's load_yaml."""
        return load_yaml(path)

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

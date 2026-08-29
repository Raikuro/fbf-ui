"""Persistence adapter orchestration service interfacing with fbf.core.persistence."""

from __future__ import annotations

from pathlib import Path

from fbf.core.persistence import SQLiteRepository, create_study_repository
from pydantic import BaseModel


def _normalize_plan_status(raw_status: str | None) -> str:
    """Normalize plan status for display.  ``None`` and ``"planned"`` become ``"pending"``."""
    if raw_status is None or raw_status == "planned":
        return "pending"
    return raw_status


class ExperimentSummaryDTO(BaseModel):
    """DTO summarizing a stored experiment for browser list display."""

    experiment_id: str
    name: str
    revision: str
    dataset_identifier: str
    horizon_months: int
    initial_wealth: str
    initial_wealth_currency: str
    created_at: str
    updated_at: str
    status: str | None
    unit_count: int | None


class ExperimentDetailDTO(BaseModel):
    """DTO providing full experiment metadata and plan list."""

    experiment_id: str
    name: str
    revision: str
    description: str
    dataset_identifier: str
    horizon_months: int
    initial_wealth: str
    initial_wealth_currency: str
    created_at: str
    updated_at: str
    plans: list[PlanSummaryDTO]


class PlanSummaryDTO(BaseModel):
    """DTO summarizing a single research plan."""

    plan_id: str
    status: str
    unit_count: int
    created_at: str
    has_results: bool


class ResultSummaryDTO(BaseModel):
    """DTO providing lightweight execution result summary."""

    result_id: str
    plan_id: str
    executed_at: str
    duration_seconds: float
    success_count: int
    failure_count: int
    total_units: int
    success_rate: float


class PersistenceService:
    """Orchestrates SQLite study repository interactions without raw SQL."""

    def open_repository(self, db_path: Path) -> SQLiteRepository:
        """Construct a StudyRepository instance for a local SQLite file."""
        return create_study_repository(str(db_path))

    def list_experiments(self, db_path: Path) -> list[ExperimentSummaryDTO]:
        """List all experiments with their latest plan status."""
        repo = self.open_repository(db_path)
        rows = repo.list_experiments_with_plans()
        return [
            ExperimentSummaryDTO(
                experiment_id=row["experiment_id"],
                name=row["name"],
                revision=row["revision"],
                dataset_identifier=row["dataset_identifier"],
                horizon_months=row["horizon_months"],
                initial_wealth=row["initial_wealth"],
                initial_wealth_currency=row["initial_wealth_currency"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                status=_normalize_plan_status(row["status"]),
                unit_count=row["unit_count"],
            )
            for row in rows
        ]

    def get_experiment_detail(
        self, db_path: Path, experiment_id: str
    ) -> ExperimentDetailDTO | None:
        """Retrieve experiment metadata and plan summaries."""
        repo = self.open_repository(db_path)
        meta = repo.get_experiment_metadata(experiment_id)
        if meta is None:
            return None

        plan_rows = repo.list_plans_for_experiment(experiment_id)
        plans = []
        for pr in plan_rows:
            result_id = repo.find_result_by_plan(pr["plan_id"])
            plans.append(
                PlanSummaryDTO(
                    plan_id=pr["plan_id"],
                    status=_normalize_plan_status(pr["status"]),
                    unit_count=pr["unit_count"],
                    created_at=pr["created_at"],
                    has_results=result_id is not None,
                )
            )

        return ExperimentDetailDTO(
            experiment_id=meta["experiment_id"],
            name=meta["name"],
            revision=meta["revision"],
            description=meta["description"],
            dataset_identifier=meta["dataset_identifier"],
            horizon_months=meta["horizon_months"],
            initial_wealth=meta["initial_wealth"],
            initial_wealth_currency=meta["initial_wealth_currency"],
            created_at=meta["created_at"],
            updated_at=meta["updated_at"],
            plans=plans,
        )

    def get_plan_result_summary(
        self, db_path: Path, plan_id: str
    ) -> ResultSummaryDTO | None:
        """Retrieve lightweight execution result summary for a plan."""
        repo = self.open_repository(db_path)
        meta = repo.get_execution_result_metadata(plan_id)
        if meta is None:
            return None

        return ResultSummaryDTO(
            result_id=meta["result_id"],
            plan_id=meta["plan_id"],
            executed_at=meta["executed_at"],
            duration_seconds=float(meta["duration_seconds"]),
            success_count=int(meta["success_count"]),
            failure_count=int(meta["failure_count"]),
            total_units=int(meta["total_units"]),
            success_rate=float(meta["success_rate"]),
        )

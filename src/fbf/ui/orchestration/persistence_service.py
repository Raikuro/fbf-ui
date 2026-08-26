"""Persistence adapter orchestration service interfacing with fbf.core.persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fbf.core.persistence import SQLiteRepository, create_study_repository
from pydantic import BaseModel, Field


class ExperimentSummaryDTO(BaseModel):
    """DTO summarizing a stored study experiment in an SQLite database."""

    experiment_id: str
    name: str
    created_at: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistenceService:
    """Orchestrates SQLite study repository interactions without raw SQL."""

    def open_repository(self, db_path: Path) -> SQLiteRepository:
        """Construct a StudyRepository instance for a local SQLite file."""
        return create_study_repository(str(db_path))

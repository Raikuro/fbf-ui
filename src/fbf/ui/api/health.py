"""Health check API router for fbf-ui."""

from __future__ import annotations

from fastapi import APIRouter
from fbf.core import __version__ as core_version
from pydantic import BaseModel

from fbf.ui import __version__ as ui_version


class HealthResponse(BaseModel):
    """Health status response payload."""

    status: str
    version: str
    core_version: str


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return application health status and installed fbf-core version."""
    return HealthResponse(
        status="ok",
        version=ui_version,
        core_version=core_version,
    )

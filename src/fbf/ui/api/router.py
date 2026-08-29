"""Root API router combining all v1 endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from fbf.ui.api.health import router as health_router
from fbf.ui.api.persistence import router as persistence_router
from fbf.ui.api.run import router as run_router
from fbf.ui.api.study import router as study_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router, tags=["health"])
api_v1_router.include_router(study_router, tags=["study"])
api_v1_router.include_router(run_router, tags=["run"])
api_v1_router.include_router(persistence_router, tags=["persistence"])

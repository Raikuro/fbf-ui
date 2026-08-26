"""Presentation web routes serving server-rendered HTML views."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fbf.core import __version__ as core_version

from fbf.ui import __version__ as ui_version

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

presentation_router = APIRouter()


def _common_context(request: Request, page_title: str, active_section: str) -> dict[str, object]:
    """Construct standard Jinja2 rendering context."""
    return {
        "request": request,
        "page_title": page_title,
        "active_section": active_section,
        "core_version": core_version,
        "ui_version": ui_version,
    }


@presentation_router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render dashboard page."""
    context = _common_context(request, page_title="Dashboard", active_section="dashboard")
    return templates.TemplateResponse(request, "dashboard.html", context)


@presentation_router.get("/study", response_class=HTMLResponse)
def study_view(request: Request) -> HTMLResponse:
    """Render study configuration page."""
    context = _common_context(request, page_title="Study Configuration", active_section="study")
    return templates.TemplateResponse(request, "study.html", context)


@presentation_router.get("/run", response_class=HTMLResponse)
def run_view(request: Request) -> HTMLResponse:
    """Render simulation run page."""
    context = _common_context(request, page_title="Simulation Run", active_section="run")
    return templates.TemplateResponse(request, "run.html", context)


@presentation_router.get("/results", response_class=HTMLResponse)
def results_view(request: Request) -> HTMLResponse:
    """Render results & visualization page."""
    context = _common_context(
        request, page_title="Results & Visualization", active_section="results"
    )
    return templates.TemplateResponse(request, "results.html", context)


@presentation_router.get("/compare", response_class=HTMLResponse)
def compare_view(request: Request) -> HTMLResponse:
    """Render strategy comparator page."""
    context = _common_context(
        request, page_title="Strategy Comparator", active_section="compare"
    )
    return templates.TemplateResponse(request, "compare.html", context)


@presentation_router.get("/persistence", response_class=HTMLResponse)
def persistence_view(request: Request) -> HTMLResponse:
    """Render SQLite persistence page."""
    context = _common_context(
        request, page_title="SQLite Persistence", active_section="persistence"
    )
    return templates.TemplateResponse(request, "persistence.html", context)

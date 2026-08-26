"""FastAPI application entrypoint for fbf-ui."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fbf.ui import __version__
from fbf.ui.api import api_v1_router
from fbf.ui.presentation import presentation_router

STATIC_DIR = Path(__file__).resolve().parent / "presentation" / "static"


def create_app() -> FastAPI:
    """Construct and configure the FastAPI web application."""
    app = FastAPI(
        title="FBF UI — FIRE Backtesting Framework",
        description="Web Interface, Application Orchestration, and Visualization for FBF.",
        version=__version__,
    )

    # Configure CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static assets directory
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Include routers
    app.include_router(api_v1_router)
    app.include_router(presentation_router)

    return app


app = create_app()


def main() -> None:
    """CLI launcher for fbf-ui web server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is required to run the fbf-ui web server.", file=sys.stderr)
        sys.exit(1)

    print(f"Starting FBF UI server v{__version__} on http://127.0.0.1:8000")
    uvicorn.run("fbf.ui.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()

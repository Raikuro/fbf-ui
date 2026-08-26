"""Presentation web routes for HTML view rendering."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

presentation_router = APIRouter()


@presentation_router.get("/", response_class=HTMLResponse)
def index() -> str:
    """Render application landing shell."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FBF UI — FIRE Backtesting Framework</title>
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            margin: 2rem;
            background: #0f172a;
            color: #f8fafc;
        }
        .card {
            background: #1e293b;
            padding: 1.5rem;
            border-radius: 0.5rem;
            border: 1px solid #334155;
        }
        h1 { color: #38bdf8; }
        code {
            background: #0f172a;
            padding: 0.2rem 0.4rem;
            border-radius: 0.25rem;
            color: #a5f3fc;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>FIRE Backtesting Framework UI (FBF UI)</h1>
        <p>Web Delivery, Application Orchestration & Visualization Layer</p>
        <p>System Status: <code>ONLINE</code></p>
        <p>API Endpoint: <a href="/api/v1/health" style="color: #38bdf8;">/api/v1/health</a></p>
    </div>
</body>
</html>
"""

"""Unit tests for presentation web routes, template rendering, and static assets."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient
from fbf.core import __version__ as core_version

from fbf.ui import __version__ as ui_version
from fbf.ui.main import create_app


def test_dashboard_route(client: TestClient) -> None:
    """Verify GET / renders dashboard with active nav state and version metadata."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "<title>Dashboard — FIRE Backtesting Framework</title>" in html
    assert 'class="nav-link active"' in html
    assert 'href="/" class="nav-link active"' in html
    assert 'href="/study" class="nav-link "' in html
    assert f"v{ui_version}" in html
    assert f"v{core_version}" in html
    assert 'href="/static/css/app.css"' in html


def test_study_route(client: TestClient) -> None:
    """Verify GET /study renders study page with study nav active."""
    response = client.get("/study")
    assert response.status_code == 200
    html = response.text
    assert "<title>Study Configuration — FIRE Backtesting Framework</title>" in html
    assert 'href="/study" class="nav-link active"' in html
    assert 'href="/" class="nav-link "' in html
    assert 'href="/run" class="nav-link "' in html
    assert "Scaffolding Placeholder" in html


def test_run_route(client: TestClient) -> None:
    """Verify GET /run renders run page with run nav active."""
    response = client.get("/run")
    assert response.status_code == 200
    html = response.text
    assert "<title>Simulation Run — FIRE Backtesting Framework</title>" in html
    assert 'href="/run" class="nav-link active"' in html
    assert 'href="/study" class="nav-link "' in html


def test_results_route(client: TestClient) -> None:
    """Verify GET /results renders results page with results nav active."""
    response = client.get("/results")
    assert response.status_code == 200
    html = response.text
    assert "<title>Results &amp; Visualization — FIRE Backtesting Framework</title>" in html
    assert 'href="/results" class="nav-link active"' in html
    assert 'href="/run" class="nav-link "' in html


def test_compare_route(client: TestClient) -> None:
    """Verify GET /compare renders compare page with compare nav active."""
    response = client.get("/compare")
    assert response.status_code == 200
    html = response.text
    assert "<title>Strategy Comparator — FIRE Backtesting Framework</title>" in html
    assert 'href="/compare" class="nav-link active"' in html


def test_persistence_route(client: TestClient) -> None:
    """Verify GET /persistence renders persistence page with persistence nav active."""
    response = client.get("/persistence")
    assert response.status_code == 200
    html = response.text
    assert "<title>SQLite Persistence — FIRE Backtesting Framework</title>" in html
    assert 'href="/persistence" class="nav-link active"' in html


def test_static_css_served(client: TestClient) -> None:
    """Verify static CSS stylesheet is served with text/css content type."""
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--bg-main:" in response.text


def test_cwd_independence(tmp_path: object) -> None:
    """Verify package-relative template and static loading works from arbitrary CWD."""
    original_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        app = create_app()
        with TestClient(app) as test_client:
            res = test_client.get("/")
            assert res.status_code == 200
            assert "<title>Dashboard — FIRE Backtesting Framework</title>" in res.text
            css_res = test_client.get("/static/css/app.css")
            assert css_res.status_code == 200
    finally:
        os.chdir(original_cwd)

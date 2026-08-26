"""Unit tests for health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient
from fbf.core import __version__ as expected_core_version

from fbf.ui import __version__ as expected_ui_version


def test_health_endpoint(client: TestClient) -> None:
    """Verify /api/v1/health returns status 200 and actual installed core version."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == expected_ui_version
    assert data["core_version"] == expected_core_version

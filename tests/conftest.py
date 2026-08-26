"""Shared pytest configuration and fixtures for fbf-ui tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from fbf.ui.main import create_app


@pytest.fixture
def client() -> Generator[TestClient]:
    """Provide a TestClient instance for FastAPI route testing."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

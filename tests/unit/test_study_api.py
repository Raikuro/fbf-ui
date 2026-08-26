"""Unit tests for YAML study loading, parsing, and path security API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

VALID_STUDY_YAML = """
metadata:
  name: Baseline Study
  description: Test backtest study configuration
  version: "1.0"
dataset:
  identifier: sp500_historical
allocation_policy:
  type: ConstantAllocationPolicy
  equity_allocation: [0.60, 0.80]
withdrawal_policy:
  type: FixedRealWithdrawalPolicy
  withdrawal_rate: [0.04]
cohorts:
  horizon_years: [30]
"""

MALFORMED_YAML = """
metadata: [invalid yaml structure : : :
"""

INVALID_SCHEMA_YAML = """
metadata:
  name: Incomplete Study
dataset:
  identifier: sp500_historical
# Missing allocation_policy, withdrawal_policy, cohorts
"""


def test_parse_text_valid(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-text parses valid YAML into StudyConfigDTO."""
    response = client.post(
        "/api/v1/study/parse-text",
        json={"yaml_content": VALID_STUDY_YAML},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Baseline Study"
    assert data["dataset_identifier"] == "sp500_historical"
    assert data["allocation_policy_type"] == "ConstantAllocationPolicy"
    assert data["allocation_policy_values"] == [0.6, 0.8]
    assert data["withdrawal_policy_values"] == [0.04]
    assert data["horizon_years"] == [30]


def test_parse_text_malformed(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-text returns 400 for malformed YAML."""
    response = client.post(
        "/api/v1/study/parse-text",
        json={"yaml_content": MALFORMED_YAML},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data["detail"]
    assert data["detail"]["error"]["code"] in ("INVALID_YAML", "INVALID_SCHEMA")


def test_parse_text_invalid_schema(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-text returns 400 for missing study schema fields."""
    response = client.post(
        "/api/v1/study/parse-text",
        json={"yaml_content": INVALID_SCHEMA_YAML},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_SCHEMA"


def test_parse_text_empty(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-text returns 400 for empty text payload."""
    response = client.post(
        "/api/v1/study/parse-text",
        json={"yaml_content": "   "},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "EMPTY_CONTENT"


def test_upload_valid(client: TestClient) -> None:
    """Verify POST /api/v1/study/upload parses valid multipart uploaded file."""
    files = {"file": ("study.yaml", VALID_STUDY_YAML.encode("utf-8"), "application/x-yaml")}
    response = client.post("/api/v1/study/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Baseline Study"
    assert data["dataset_identifier"] == "sp500_historical"


def test_upload_empty(client: TestClient) -> None:
    """Verify POST /api/v1/study/upload returns 400 for empty file upload."""
    files = {"file": ("empty.yaml", b"", "application/x-yaml")}
    response = client.post("/api/v1/study/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "EMPTY_CONTENT"


def test_upload_file_too_large(client: TestClient) -> None:
    """Verify POST /api/v1/study/upload returns 400 for file exceeding 2MB."""
    oversized = b"a" * (2 * 1024 * 1024 + 1)
    files = {"file": ("large.yaml", oversized, "application/x-yaml")}
    response = client.post("/api/v1/study/upload", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "FILE_TOO_LARGE"


def test_parse_path_valid(client: TestClient, tmp_path: Path) -> None:
    """Verify POST /api/v1/study/parse-path parses permitted server file."""
    # Write a test file within project workspace
    test_file = Path.cwd() / "tests" / "fixtures" / "sample_study.yaml"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(VALID_STUDY_YAML, encoding="utf-8")
    try:
        rel_path = str(test_file.relative_to(Path.cwd()))
        response = client.post(
            "/api/v1/study/parse-path",
            json={"path": rel_path},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Baseline Study"
    finally:
        if test_file.exists():
            test_file.unlink()


def test_parse_path_not_found(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-path returns 404 for non-existent file."""
    response = client.post(
        "/api/v1/study/parse-path",
        json={"path": "tests/fixtures/non_existent_file.yaml"},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "FILE_NOT_FOUND"


def test_parse_path_forbidden_traversal(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-path returns 403 for path traversal escaping workspace."""
    response = client.post(
        "/api/v1/study/parse-path",
        json={"path": "../../etc/passwd"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["detail"]["error"]["code"] == "PATH_FORBIDDEN"


def test_parse_path_directory(client: TestClient) -> None:
    """Verify POST /api/v1/study/parse-path returns 400 when path is a directory."""
    response = client.post(
        "/api/v1/study/parse-path",
        json={"path": "tests"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "IS_DIRECTORY"

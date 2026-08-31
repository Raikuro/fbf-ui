"""P11 Stage 5 tests: cohort heatmap frontend integration."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fbf.core.persistence.studies.sqlite import SQLiteRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return "2026-01-01T00:00:00Z"


def _to_canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_stats_json(success: bool, final_wealth: str = "500000.00") -> str:
    return json.dumps({
        "final_wealth_amount": final_wealth,
        "final_wealth_currency": "EUR",
        "max_drawdown": 0.05,
        "success": success,
        "failure_month": None if success else 24,
        "months_simulated": 360,
        "execution_time_seconds": 0.01,
    }, sort_keys=True, separators=(",", ":"))


def _seed_p11_database(
    conn: sqlite3.Connection,
    result_id: str | None = None,
    experiment_name: str = "p11-fe-test",
) -> str:
    """Seed a database with P11-style data for frontend tests."""
    if result_id is None:
        result_id = _uuid()

    from fbf.core.persistence.studies.sqlite.schema import ALL_DDL, INDEX_DDL
    for statement in ALL_DDL:
        conn.execute(statement)
    for statement in INDEX_DDL:
        conn.execute(statement)

    experiment_id = _uuid()
    plan_id = _uuid()
    cohorts = ["2000-01-01", "2001-01-01"]
    equities = [0.5, 0.7]
    rates = [0.03, 0.04]
    horizons = [30, 40]

    conn.execute(
        "INSERT INTO experiments (experiment_id, name, revision, description, "
        "dataset_identifier, horizon_months, initial_wealth, "
        "initial_wealth_currency, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (experiment_id, experiment_name, "v1", "P11 FE test",
         "test", 721, "1000000", "EUR", _now_iso(), _now_iso()),
    )

    cohort_ids: list[str] = []
    for d in cohorts:
        cid = _uuid()
        cohort_ids.append(cid)
        conn.execute(
            "INSERT INTO cohorts (cohort_id, experiment_id, start_date, "
            "cohort_ref, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, experiment_id, d, d, _now_iso()),
        )

    param_config_map: dict[tuple[float, float, int], str] = {}
    for eq in equities:
        for wr in rates:
            for hy in horizons:
                params = {"equity_allocation": eq, "withdrawal_rate": wr, "horizon_years": hy}
                pj = _to_canonical_json(params)
                ph = _hash(pj)
                existing = conn.execute(
                    "SELECT param_config_id FROM parameter_configurations WHERE params_hash = ?",
                    (ph,),
                ).fetchone()
                if existing:
                    pcid = existing[0]
                else:
                    pcid = _uuid()
                    conn.execute(
                        "INSERT INTO parameter_configurations "
                        "(param_config_id, params_json, params_hash, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (pcid, pj, ph, _now_iso()),
                    )
                param_config_map[(eq, wr, hy)] = pcid

    alloc_pid = _uuid()
    withdraw_pid = _uuid()
    conn.execute(
        "INSERT INTO policies (policy_id, policy_type, params_json, params_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (alloc_pid, "allocation", "{}", _hash("{}"), _now_iso()),
    )
    conn.execute(
        "INSERT INTO policies (policy_id, policy_type, params_json, params_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (withdraw_pid, "withdrawal", "{}", _hash("{}"), _now_iso()),
    )

    unit_count = len(cohorts) * len(equities) * len(rates) * len(horizons)
    conn.execute(
        "INSERT INTO research_plans "
        "(plan_id, experiment_id, created_at, unit_count, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (plan_id, experiment_id, _now_iso(), unit_count, "completed"),
    )

    unit_index = 0
    for ci, cid in enumerate(cohort_ids):
        for eq in equities:
            for wr in rates:
                for hy in horizons:
                    pcid = param_config_map[(eq, wr, hy)]
                    uid = _uuid()
                    conn.execute(
                        "INSERT INTO planned_units "
                        "(unit_id, plan_id, unit_index, cohort_id, "
                        "param_config_id, allocation_policy_id, "
                        "withdrawal_policy_id, initial_portfolio_json, "
                        "final_value_target) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (uid, plan_id, unit_index, cid, pcid,
                         alloc_pid, withdraw_pid, "{}", None),
                    )
                    success = (hash(f"{ci}-{eq}-{wr}-{hy}") % 100) < 70
                    fw = str(500000 + hash(f"w-{ci}-{eq}-{wr}-{hy}") % 1000000)
                    stats_json = _make_stats_json(success, fw)
                    conn.execute(
                        "INSERT INTO simulation_results "
                        "(execution_result_id, unit_index, month_index, "
                        "monthly_payload_json, statistics_payload_json, "
                        "final_month) VALUES (?, ?, ?, ?, ?, ?)",
                        (result_id, unit_index, 0, '{"dummy":true}', stats_json, 1),
                    )
                    unit_index += 1

    conn.execute(
        "INSERT INTO execution_results "
        "(result_id, plan_id, executed_at, duration_seconds, "
        "success_count, failure_count, total_units) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (result_id, plan_id, _now_iso(), 1.0, 0, 0, unit_index),
    )
    conn.commit()
    return result_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "test_p11_fe.db"
    SQLiteRepository(str(db_file))

    import fbf.ui.api.persistence as persistence_module
    import fbf.ui.config

    original_db = fbf.ui.config._DEFAULT_DB_PATH
    original_api_db = persistence_module._DEFAULT_DB_PATH
    fbf.ui.config._DEFAULT_DB_PATH = db_file
    persistence_module._DEFAULT_DB_PATH = db_file

    from fbf.ui.main import create_app
    app = create_app()
    test_client = TestClient(app)

    yield test_client
    fbf.ui.config._DEFAULT_DB_PATH = original_db
    persistence_module._DEFAULT_DB_PATH = original_api_db


@pytest.fixture
def seeded_client(tmp_path: Path) -> tuple[TestClient, str]:
    db_file = tmp_path / "test_p11_fe.db"
    with sqlite3.connect(str(db_file)) as conn:
        result_id = _seed_p11_database(conn)

    import fbf.ui.api.persistence as persistence_module
    import fbf.ui.config

    original_db = fbf.ui.config._DEFAULT_DB_PATH
    original_api_db = persistence_module._DEFAULT_DB_PATH
    fbf.ui.config._DEFAULT_DB_PATH = db_file
    persistence_module._DEFAULT_DB_PATH = db_file

    from fbf.ui.main import create_app
    app = create_app()
    test_client = TestClient(app)

    yield test_client, result_id
    fbf.ui.config._DEFAULT_DB_PATH = original_db
    persistence_module._DEFAULT_DB_PATH = original_api_db


# ===========================================================================
# 1. Template Rendering
# ===========================================================================


class TestTemplateRendering:
    def test_cohort_heatmap_card_present(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "cohort-heatmap-card" in response.text

    def test_parameter_selector_present(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "p11-param-select" in response.text

    def test_heatmap_canvas_present(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "cohort-heatmap-chart" in response.text

    def test_chartjs_matrix_dependency_loaded(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "chartjs-chart-matrix" in response.text

    def test_p11_loading_element_present(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "p11-loading" in response.text

    def test_p11_empty_element_present(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "p11-empty" in response.text

    def test_p11_error_element_present(self, client: TestClient) -> None:
        response = client.get("/results/test-id")
        assert response.status_code == 200
        assert "p11-error" in response.text


# ===========================================================================
# 2. API Integration
# ===========================================================================


class TestAPIIntegration:
    def test_parameters_endpoint_accessible(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/api/v1/persistence/results/{result_id}/parameters",
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["parameters"]) == 4

    def test_cohort_grid_endpoint_accessible(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/api/v1/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.03},
        )
        assert response.status_code == 200
        data = response.json()
        assert "cohorts" in data
        assert "horizons" in data
        assert "grid" in data


# ===========================================================================
# 3. Missing/Empty/Error Behavior
# ===========================================================================


class TestMissingEmptyBehavior:
    def test_missing_result_parameters_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/persistence/results/nonexistent/parameters")
        assert response.status_code == 404

    def test_missing_result_cohort_grid_returns_404(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/persistence/results/nonexistent/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        )
        assert response.status_code == 404

    def test_results_page_renders_for_any_id(self, client: TestClient) -> None:
        response = client.get("/results/completely-invalid-id")
        assert response.status_code == 200
        assert "cohort-heatmap-card" in response.text

"""P11 API tests: parameters and cohort-grid endpoints."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fbf.core.persistence.studies.sqlite import SQLiteRepository

from fbf.ui.api.persistence import router

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


def _make_stats_json(
    success: bool,
    final_wealth: str = "500000.00",
    failure_month: int | None = None,
) -> str:
    return json.dumps({
        "final_wealth_amount": final_wealth,
        "final_wealth_currency": "EUR",
        "max_drawdown": 0.05,
        "success": success,
        "failure_month": failure_month,
        "months_simulated": 360,
        "execution_time_seconds": 0.01,
    }, sort_keys=True, separators=(",", ":"))


def _make_cohort_date(index: int) -> date:
    base_year = 2000
    total_months = base_year * 12 + index
    year = (total_months - 1) // 12
    month = ((total_months - 1) % 12) + 1
    return date(year, month, 1)


def _seed_p11_database(
    conn: sqlite3.Connection,
    cohorts: list[date],
    equity_allocations: list[float],
    withdrawal_rates: list[float],
    horizon_years: list[int],
    result_id: str | None = None,
    experiment_name: str = "p11-test",
) -> str:
    """Seed a database with P11-style data. Returns the result_id."""
    if result_id is None:
        result_id = _uuid()

    # Ensure schema exists
    from fbf.core.persistence.studies.sqlite.schema import ALL_DDL, INDEX_DDL
    for statement in ALL_DDL:
        conn.execute(statement)
    for statement in INDEX_DDL:
        conn.execute(statement)

    experiment_id = _uuid()
    plan_id = _uuid()

    conn.execute(
        "INSERT INTO experiments (experiment_id, name, revision, description, "
        "dataset_identifier, horizon_months, initial_wealth, "
        "initial_wealth_currency, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (experiment_id, experiment_name, "v1", "P11 test",
         "test", 721, "1000000", "EUR", _now_iso(), _now_iso()),
    )

    cohort_ids: list[str] = []
    for d in cohorts:
        cid = _uuid()
        cohort_ids.append(cid)
        conn.execute(
            "INSERT INTO cohorts (cohort_id, experiment_id, start_date, "
            "cohort_ref, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, experiment_id, d.isoformat(), d.isoformat(), _now_iso()),
        )

    param_config_map: dict[tuple[float, float, int], str] = {}
    for eq in equity_allocations:
        for wr in withdrawal_rates:
            for hy in horizon_years:
                params = {
                    "equity_allocation": eq,
                    "withdrawal_rate": wr,
                    "horizon_years": hy,
                }
                pj = _to_canonical_json(params)
                ph = _hash(pj)
                existing = conn.execute(
                    "SELECT param_config_id FROM parameter_configurations "
                    "WHERE params_hash = ?",
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
    existing_alloc = conn.execute(
        "SELECT policy_id FROM policies "
        "WHERE policy_type = 'allocation' AND params_hash = ?",
        (_hash("{}"),),
    ).fetchone()
    if existing_alloc:
        alloc_pid = existing_alloc[0]
    else:
        conn.execute(
            "INSERT INTO policies "
            "(policy_id, policy_type, params_json, params_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (alloc_pid, "allocation", "{}", _hash("{}"), _now_iso()),
        )
    existing_withdraw = conn.execute(
        "SELECT policy_id FROM policies "
        "WHERE policy_type = 'withdrawal' AND params_hash = ?",
        (_hash("{}"),),
    ).fetchone()
    if existing_withdraw:
        withdraw_pid = existing_withdraw[0]
    else:
        conn.execute(
            "INSERT INTO policies "
            "(policy_id, policy_type, params_json, params_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (withdraw_pid, "withdrawal", "{}", _hash("{}"), _now_iso()),
        )

    unit_count = (
        len(cohorts) * len(equity_allocations)
        * len(withdrawal_rates) * len(horizon_years)
    )
    conn.execute(
        "INSERT INTO research_plans "
        "(plan_id, experiment_id, created_at, unit_count, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (plan_id, experiment_id, _now_iso(), unit_count, "completed"),
    )

    unit_index = 0
    for ci, cid in enumerate(cohort_ids):
        for eq in equity_allocations:
            for wr in withdrawal_rates:
                for hy in horizon_years:
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
                    fm = (
                        None if success
                        else (hash(f"fm-{ci}-{eq}-{wr}-{hy}") % 360) + 1
                    )
                    fw = str(500000 + hash(f"w-{ci}-{eq}-{wr}-{hy}") % 1000000)
                    stats_json = _make_stats_json(success, fw, fm)

                    conn.execute(
                        "INSERT INTO simulation_results "
                        "(execution_result_id, unit_index, month_index, "
                        "monthly_payload_json, statistics_payload_json, "
                        "final_month) VALUES (?, ?, ?, ?, ?, ?)",
                        (result_id, unit_index, 0,
                         '{"dummy":true}', stats_json, 1),
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
    db_file = tmp_path / "test_p11_api.db"
    SQLiteRepository(str(db_file))

    import fbf.ui.api.persistence as persistence_module

    original = persistence_module._DEFAULT_DB_PATH
    persistence_module._DEFAULT_DB_PATH = db_file

    app = __import__("fastapi", fromlist=["FastAPI"]).FastAPI()
    app.include_router(router)
    test_client = TestClient(app)

    yield test_client

    persistence_module._DEFAULT_DB_PATH = original


@pytest.fixture
def seeded_client(tmp_path: Path) -> tuple[TestClient, str]:
    """Create a client with seeded P11 data. Returns (client, result_id)."""
    db_file = tmp_path / "test_p11_api.db"

    cohorts = [_make_cohort_date(0), _make_cohort_date(1)]
    equities = [0.0, 0.5]
    rates = [0.03, 0.04]
    horizons = [30, 40]

    with sqlite3.connect(str(db_file)) as conn:
        result_id = _seed_p11_database(
            conn, cohorts, equities, rates, horizons,
        )

    import fbf.ui.api.persistence as persistence_module

    original = persistence_module._DEFAULT_DB_PATH
    persistence_module._DEFAULT_DB_PATH = db_file

    app = __import__("fastapi", fromlist=["FastAPI"]).FastAPI()
    app.include_router(router)
    test_client = TestClient(app)

    yield test_client, result_id

    persistence_module._DEFAULT_DB_PATH = original


# ===========================================================================
# GET /results/{result_id}/parameters
# ===========================================================================


class TestAvailableParametersEndpoint:
    def test_200_with_valid_result(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/parameters",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result_id"] == result_id
        assert len(body["parameters"]) == 4
        for p in body["parameters"]:
            assert "equity_allocation" in p
            assert "withdrawal_rate" in p
            assert "horizon_years" not in p

    def test_404_for_missing_result(
        self, client: TestClient,
    ) -> None:
        response = client.get(
            "/persistence/results/nonexistent/parameters",
        )
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["error"]["code"] == "RESULT_NOT_FOUND"

    def test_response_schema(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/parameters",
        )
        assert response.status_code == 200
        body = response.json()
        assert "result_id" in body
        assert "parameters" in body
        assert isinstance(body["parameters"], list)
        for p in body["parameters"]:
            assert isinstance(p, dict)
            assert isinstance(p["equity_allocation"], (int, float))
            assert isinstance(p["withdrawal_rate"], (int, float))

    def test_unique_selectors(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/parameters",
        )
        assert response.status_code == 200
        body = response.json()
        values = {
            (p["equity_allocation"], p["withdrawal_rate"])
            for p in body["parameters"]
        }
        assert len(values) == len(body["parameters"])


# ===========================================================================
# GET /results/{result_id}/cohort-grid
# ===========================================================================


class TestCohortGridEndpoint:
    def test_200_with_valid_params(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result_id"] == result_id
        assert body["parameters"] == {
            "equity_allocation": 0.5,
            "withdrawal_rate": 0.04,
        }
        assert len(body["cohorts"]) == 2
        assert body["horizons"] == [30, 40]
        assert body["total_units"] == 4

    def test_400_missing_equity_allocation(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"withdrawal_rate": 0.04},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "INVALID_PARAMETERS"

    def test_400_missing_withdrawal_rate(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.5},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "INVALID_PARAMETERS"

    def test_400_missing_both_params(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "INVALID_PARAMETERS"

    def test_404_for_missing_result(
        self, client: TestClient,
    ) -> None:
        response = client.get(
            "/persistence/results/nonexistent/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["error"]["code"] == "RESULT_NOT_FOUND"

    def test_400_for_non_matching_params(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.99, "withdrawal_rate": 0.99},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "PARAMETER_NOT_FOUND"

    def test_response_schema(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        )
        assert response.status_code == 200
        body = response.json()
        assert "result_id" in body
        assert "cohorts" in body
        assert "horizons" in body
        assert "parameters" in body
        assert "grid" in body
        assert "total_units" in body
        assert "success_count" in body
        assert "failure_count" in body
        assert "success" in body["grid"]
        assert "failure_month" in body["grid"]
        assert "terminal_wealth" in body["grid"]

    def test_grid_dimensions(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["grid"]["success"]) == 2
        for row in body["grid"]["success"]:
            assert len(row) == 2

    def test_ordering(
        self, seeded_client: tuple[TestClient, str],
    ) -> None:
        client, result_id = seeded_client
        response = client.get(
            f"/persistence/results/{result_id}/cohort-grid",
            params={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["cohorts"] == sorted(body["cohorts"])
        assert body["horizons"] == sorted(body["horizons"])

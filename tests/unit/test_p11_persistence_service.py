"""Tests for P11 PersistenceService methods.

Tests get_result_parameters() and get_result_cohort_grid() on PersistenceService.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fbf.core.persistence.studies.sqlite import SQLiteRepository

from fbf.ui.orchestration.persistence_service import (
    AvailableParametersDTO,
    CohortGridDataDTO,
    CohortGridDTO,
    ParameterSelectorDTO,
    PersistenceService,
)

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
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_p11_service.db"


@pytest.fixture
def service() -> PersistenceService:
    return PersistenceService()


@pytest.fixture
def seeded_result(db_path: Path) -> tuple[str, dict[str, Any]]:
    """Seed a database with 2 cohorts, 2 equities, 2 rates, 2 horizons."""
    cohorts = [_make_cohort_date(0), _make_cohort_date(1)]
    equities = [0.0, 0.5]
    rates = [0.03, 0.04]
    horizons = [30, 40]

    with sqlite3.connect(str(db_path)) as conn:
        result_id = _seed_p11_database(
            conn, cohorts, equities, rates, horizons,
        )

    return result_id, {
        "cohorts": [d.isoformat() for d in cohorts],
        "equities": equities,
        "rates": rates,
        "horizons": horizons,
    }


# ---------------------------------------------------------------------------
# TestAvailableParametersDTO
# ---------------------------------------------------------------------------


class TestAvailableParametersDTO:
    def test_dto_structure(self) -> None:
        dto = AvailableParametersDTO(
            result_id="test-id",
            parameters=[
                ParameterSelectorDTO(
                    equity_allocation=0.5,
                    withdrawal_rate=0.04,
                ),
            ],
        )
        assert dto.result_id == "test-id"
        assert len(dto.parameters) == 1
        assert dto.parameters[0].equity_allocation == 0.5
        assert dto.parameters[0].withdrawal_rate == 0.04

    def test_dto_serialization(self) -> None:
        dto = AvailableParametersDTO(
            result_id="test-id",
            parameters=[
                ParameterSelectorDTO(
                    equity_allocation=0.5,
                    withdrawal_rate=0.04,
                ),
            ],
        )
        data = dto.model_dump()
        assert data["result_id"] == "test-id"
        assert data["parameters"][0]["equity_allocation"] == 0.5
        assert data["parameters"][0]["withdrawal_rate"] == 0.04


# ---------------------------------------------------------------------------
# TestCohortGridDTO
# ---------------------------------------------------------------------------


class TestCohortGridDTO:
    def test_dto_structure(self) -> None:
        dto = CohortGridDTO(
            result_id="test-id",
            cohorts=["2000-01-01"],
            horizons=[30],
            parameters={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
            grid=CohortGridDataDTO(
                success=[[True]],
                failure_month=[[None]],
                terminal_wealth=[[500000.0]],
            ),
            total_units=1,
            success_count=1,
            failure_count=0,
        )
        assert dto.result_id == "test-id"
        assert dto.cohorts == ["2000-01-01"]
        assert dto.horizons == [30]
        assert dto.parameters == {"equity_allocation": 0.5, "withdrawal_rate": 0.04}
        assert dto.grid.success == [[True]]
        assert dto.grid.failure_month == [[None]]
        assert dto.grid.terminal_wealth == [[500000.0]]
        assert dto.total_units == 1
        assert dto.success_count == 1
        assert dto.failure_count == 0

    def test_dto_serialization(self) -> None:
        dto = CohortGridDTO(
            result_id="test-id",
            cohorts=["2000-01-01"],
            horizons=[30],
            parameters={"equity_allocation": 0.5, "withdrawal_rate": 0.04},
            grid=CohortGridDataDTO(
                success=[[True]],
                failure_month=[[None]],
                terminal_wealth=[[500000.0]],
            ),
            total_units=1,
            success_count=1,
            failure_count=0,
        )
        data = dto.model_dump()
        assert data["result_id"] == "test-id"
        assert data["grid"]["success"] == [[True]]
        assert data["grid"]["failure_month"] == [[None]]
        assert data["grid"]["terminal_wealth"] == [[500000.0]]


# ---------------------------------------------------------------------------
# TestPersistenceService.get_result_parameters
# ---------------------------------------------------------------------------


class TestGetResultParameters:
    def test_returns_available_parameters_dto(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        dto = service.get_result_parameters(db_path, result_id)
        assert dto is not None
        assert isinstance(dto, AvailableParametersDTO)
        assert dto.result_id == result_id
        # 2 equities × 2 rates = 4 selectors
        assert len(dto.parameters) == 4
        for p in dto.parameters:
            assert isinstance(p, ParameterSelectorDTO)
            assert hasattr(p, "equity_allocation")
            assert hasattr(p, "withdrawal_rate")

    def test_returns_none_for_missing_result(
        self, service: PersistenceService, db_path: Path,
    ) -> None:
        SQLiteRepository(str(db_path))
        assert service.get_result_parameters(
            db_path, "nonexistent-id",
        ) is None

    def test_correct_parameter_values(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        dto = service.get_result_parameters(db_path, result_id)
        assert dto is not None
        values = {
            (p.equity_allocation, p.withdrawal_rate)
            for p in dto.parameters
        }
        assert values == {
            (0.0, 0.03), (0.0, 0.04), (0.5, 0.03), (0.5, 0.04),
        }

    def test_multiple_horizons_produce_one_selector(
        self, service: PersistenceService, db_path: Path,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30, 40, 50, 60]

        with sqlite3.connect(str(db_path)) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        dto = service.get_result_parameters(db_path, result_id)
        assert dto is not None
        assert len(dto.parameters) == 1
        assert dto.parameters[0].equity_allocation == 0.5
        assert dto.parameters[0].withdrawal_rate == 0.04


# ---------------------------------------------------------------------------
# TestPersistenceService.get_result_cohort_grid
# ---------------------------------------------------------------------------


class TestGetResultCohortGrid:
    def test_returns_cohort_grid_dto(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        dto = service.get_result_cohort_grid(
            db_path, result_id, 0.5, 0.04,
        )
        assert dto is not None
        assert isinstance(dto, CohortGridDTO)
        assert dto.result_id == result_id
        assert dto.parameters == {
            "equity_allocation": 0.5,
            "withdrawal_rate": 0.04,
        }

    def test_grid_dimensions(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        dto = service.get_result_cohort_grid(
            db_path, result_id, 0.5, 0.04,
        )
        assert dto is not None
        assert len(dto.cohorts) == 2
        assert dto.horizons == [30, 40]
        assert dto.total_units == 4
        assert len(dto.grid.success) == 2
        for row in dto.grid.success:
            assert len(row) == 2

    def test_returns_none_for_missing_result(
        self, service: PersistenceService, db_path: Path,
    ) -> None:
        SQLiteRepository(str(db_path))
        assert service.get_result_cohort_grid(
            db_path, "nonexistent-id", 0.5, 0.04,
        ) is None

    def test_returns_none_for_non_matching_params(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        assert service.get_result_cohort_grid(
            db_path, result_id, 0.99, 0.99,
        ) is None

    def test_all_horizons_included(
        self, service: PersistenceService, db_path: Path,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30, 40, 50, 60]

        with sqlite3.connect(str(db_path)) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        dto = service.get_result_cohort_grid(
            db_path, result_id, 0.5, 0.04,
        )
        assert dto is not None
        assert dto.horizons == [30, 40, 50, 60]
        assert dto.total_units == 4

    def test_success_count_plus_failure_count_equals_total(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        dto = service.get_result_cohort_grid(
            db_path, result_id, 0.5, 0.04,
        )
        assert dto is not None
        assert (
            dto.success_count + dto.failure_count
            == dto.total_units
        )

    def test_dto_serialization_preserves_values(
        self,
        service: PersistenceService,
        db_path: Path,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        dto = service.get_result_cohort_grid(
            db_path, result_id, 0.5, 0.04,
        )
        assert dto is not None
        data = dto.model_dump()
        assert data["result_id"] == result_id
        assert data["cohorts"] == dto.cohorts
        assert data["horizons"] == dto.horizons
        assert data["parameters"] == dto.parameters
        assert data["grid"]["success"] == dto.grid.success
        assert data["grid"]["failure_month"] == dto.grid.failure_month
        assert data["grid"]["terminal_wealth"] == dto.grid.terminal_wealth
        assert data["total_units"] == dto.total_units
        assert data["success_count"] == dto.success_count
        assert data["failure_count"] == dto.failure_count

"""P10 API tests: result summary, statistics, and trajectory endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    ExperimentRun,
    SimulationResult,
    SimulationStatistics,
    SimulationTimeline,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.persistence.studies.sqlite import SQLiteRepository
from fbf.core.persistence.studies.sqlite.codecs import SimulationResultCodec
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

from fbf.ui.api.persistence import router

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


# ---------------------------------------------------------------------------
# Dataset / policy / codec helpers (same pattern as P8 tests)
# ---------------------------------------------------------------------------


def _make_dataset() -> Dataset:
    snapshots = []
    for i in range(240):
        m = i + 1
        y = 2000 + (m - 1) // 12
        mo = ((m - 1) % 12) + 1
        snapshots.append(
            MarketSnapshot(
                date=date(y, mo, 1),
                index_levels={_ASSET: Decimal("100.00")},
                inflation=Decimal("0.00"),
                inflation_cumulative=Decimal("0.00"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100.00"),
            )
        )
    return Dataset(snapshots=snapshots, frequency="monthly", version="TEST_v1")


_TEST_DATASET = _make_dataset()


class DummyAllocationPolicy(AllocationPolicy):
    def decide(self, context: object) -> AllocationDecision:
        return AllocationDecision(reason="dummy", allocation_target=AllocationTarget(weights={}))


class DummyWithdrawalPolicy(WithdrawalPolicy):
    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="dummy",
            nominal_amount=Money(Decimal("500"), Currency.EUR),
            real_amount=Money(Decimal("500"), Currency.EUR),
        )


class DummyDatasetResolver:
    def resolve(self, dataset_identifier: str) -> Dataset:
        return _TEST_DATASET


class DummyAllocationPolicyCodec:
    policy_type: str = "AllocationPolicy"

    def dump(self, policy: object) -> dict[str, object]:
        return {"type": "AllocationPolicy"}

    def load(self, parameters: dict[str, object]) -> DummyAllocationPolicy:
        return DummyAllocationPolicy()


class DummyWithdrawalPolicyCodec:
    policy_type: str = "WithdrawalPolicy"

    def dump(self, policy: object) -> dict[str, object]:
        return {"type": "WithdrawalPolicy"}

    def load(self, parameters: dict[str, object]) -> DummyWithdrawalPolicy:
        return DummyWithdrawalPolicy()


def _make_context() -> PersistenceReconstructionContext:
    return PersistenceReconstructionContext(
        dataset_resolver=DummyDatasetResolver(),
        policy_codecs={
            ("allocation", "AllocationPolicy"): DummyAllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): DummyWithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )


def _make_experiment(name: str = "p10-api-test") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="P10 API test experiment",
        dataset=_TEST_DATASET,
        horizon_months=120,
        initial_wealth=Money(Decimal("500000.00"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=date(2000, 1, 1)),),
        allocation_policies=(DummyAllocationPolicy(),),
        withdrawal_policies=(DummyWithdrawalPolicy(),),
    )


def _make_unit(month: int = 1) -> PlannedSimulationUnit:
    cohort_date = date(2000, month, 1)
    sliced = _TEST_DATASET.slice(cohort_date, 120)
    return PlannedSimulationUnit(
        cohort=CohortSpecification(start_date=cohort_date),
        parameter_config=ParameterConfiguration(values={"rate": 0.04}),
        allocation_policy=DummyAllocationPolicy(),
        withdrawal_policy=DummyWithdrawalPolicy(),
        initial_portfolio=Portfolio(
            holdings=(AssetHolding(asset_class=_ASSET, units=Decimal("1000")),)
        ),
        dataset=sliced,
    )


def _make_plan(num_units: int = 3) -> ResearchPlan:
    experiment = _make_experiment()
    units = tuple(_make_unit(month=((i % 12) + 1)) for i in range(num_units))
    return ResearchPlan(experiment_definition=experiment, units=units)


def _save_result(
    repo: SQLiteRepository,
    plan: ResearchPlan,
    sim_results: tuple[SimulationResult, ...],
    ctx: PersistenceReconstructionContext,
    name: str = "p10-api-test",
) -> str:
    sim_contexts = tuple(
        SimulationContext(
            experiment_name=plan.experiment_definition.name,
            cohort=unit.cohort.start_date.isoformat(),
            start_date=unit.cohort.start_date,
            horizon_months=plan.experiment_definition.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=_TEST_DATASET,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        for unit in plan.units
    )
    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description=plan.experiment_definition.description,
        simulation_contexts=sim_contexts,
    )
    exp_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    research_result = ResearchExecutionResult(plan=plan, experiment_result=exp_run)
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=name, revision="v1"),
        plan.experiment_definition,
        ctx,
    )
    plan_id = repo.save_plan(plan, exp_id, ctx)
    return repo.save_execution_result(plan_id, research_result, ctx, duration_seconds=0.5)


def _make_sim_result(
    final_wealth: str = "500000",
    success: bool = True,
    failure_month: int | None = None,
    months_simulated: int = 12,
    portfolio_values: list[float] | None = None,
) -> SimulationResult:
    if portfolio_values is None:
        return SimulationResult(
            timeline=SimulationTimeline(monthly_results=()),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal(final_wealth), Currency.EUR),
                max_drawdown=0.05,
                success=success,
                failure_month=failure_month,
                months_simulated=months_simulated,
                execution_time_seconds=0.01,
            ),
        )
    from fbf.core.domain.model.market_snapshot import MarketSnapshot as MS
    from fbf.core.execution.pipeline.simulation import MonthlyResult

    monthly_results = []
    for i, pv in enumerate(portfolio_values):
        ms = MS(
            date=date(2000, 1 + (i % 12), 1),
            index_levels={_ASSET: Decimal("100.00")},
            inflation=Decimal("0.00"),
            inflation_cumulative=Decimal("0.00"),
            is_ath=True,
            is_underwater=False,
            running_ath=Decimal("100.00"),
        )
        portfolio = Portfolio(
            holdings=(AssetHolding(asset_class=_ASSET, units=Decimal(str(pv))),)
        )
        mr = MonthlyResult(
            date=date(2000, 1 + (i % 12), 1),
            period_index=i,
            market_snapshot=ms,
            portfolio=portfolio,
            allocation=None,
            allocation_target=None,
            allocation_drift=None,
            withdrawal_decision=None,
            rebalance_result=None,
            drawdown=0.0,
            cumulative_return=0.0,
            cumulative_inflation=0.0,
            events=(),
        )
        monthly_results.append(mr)

    return SimulationResult(
        timeline=SimulationTimeline(monthly_results=tuple(monthly_results)),
        statistics=SimulationStatistics(
            final_wealth=Money(Decimal(final_wealth), Currency.EUR),
            max_drawdown=0.05,
            success=success,
            failure_month=failure_month,
            months_simulated=months_simulated,
            execution_time_seconds=0.01,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "test_p10_api.db"
    SQLiteRepository(str(db_file))

    import fbf.ui.api.persistence as persistence_module

    original = persistence_module._DEFAULT_DB_PATH
    persistence_module._DEFAULT_DB_PATH = db_file

    app = __import__("fastapi", fromlist=["FastAPI"]).FastAPI()
    app.include_router(router)
    test_client = TestClient(app)

    yield test_client

    persistence_module._DEFAULT_DB_PATH = original


# ===========================================================================
# GET /results/{result_id}/summary
# ===========================================================================


class TestResultSummaryEndpoint:
    def test_missing_result_returns_404(self, client: TestClient) -> None:
        response = client.get("/persistence/results/nonexistent/summary")
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["error"]["code"] == "RESULT_NOT_FOUND"

    def test_returns_summary_for_existing_result(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=4)
        sim_results = tuple(
            _make_sim_result(str(500000 + i * 1000), success=i < 3)
            for i in range(4)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(f"/persistence/results/{result_id}/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["result_id"] == result_id
        assert data["total_units"] == 4
        assert data["success_count"] == 3
        assert data["failure_count"] == 1
        assert "success_rate" in data
        assert "executed_at" in data


# ===========================================================================
# GET /results/{result_id}/statistics
# ===========================================================================


class TestResultStatisticsEndpoint:
    def test_missing_result_returns_404(self, client: TestClient) -> None:
        response = client.get("/persistence/results/nonexistent/statistics")
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["error"]["code"] == "RESULT_NOT_FOUND"

    def test_returns_statistics_for_existing_result(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=5)
        sim_results = tuple(
            _make_sim_result(
                str(100000 * (i + 1)),
                success=i < 3,
                failure_month=None if i < 3 else 24,
            )
            for i in range(5)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(f"/persistence/results/{result_id}/statistics")
        assert response.status_code == 200
        data = response.json()
        assert data["result_id"] == result_id
        assert data["total_units"] == 5
        assert data["success_count"] == 3
        assert data["failure_count"] == 2
        # Check terminal wealth structure
        tw = data["terminal_wealth"]
        assert "min" in tw
        assert "max" in tw
        assert "mean" in tw
        assert "median" in tw
        assert "p10" in tw
        assert "p90" in tw
        # Check failure months histogram
        hist = data["failure_months"]["histogram"]
        assert len(hist) == 1
        assert hist[0]["month"] == 24
        assert hist[0]["count"] == 2


# ===========================================================================
# GET /results/{result_id}/trajectory
# ===========================================================================


class TestResultTrajectoryEndpoint:
    def test_missing_result_returns_404(self, client: TestClient) -> None:
        response = client.get("/persistence/results/nonexistent/trajectory")
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["error"]["code"] == "RESULT_NOT_FOUND"

    def test_returns_trajectory_with_default_percentiles(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=3)
        sim_results = tuple(
            _make_sim_result(
                str(120000), months_simulated=6,
                portfolio_values=[100000 + i * 4000 for i in range(6)],
            )
            for _ in range(3)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(f"/persistence/results/{result_id}/trajectory")
        assert response.status_code == 200
        data = response.json()
        assert data["result_id"] == result_id
        assert data["total_units"] == 3
        assert data["month_count"] == 6
        assert len(data["months"]) == 6
        # Default percentiles
        assert data["percentiles"] == [10.0, 25.0, 50.0, 75.0, 90.0]
        assert "p10" in data["series"]
        assert "p50" in data["series"]
        assert "p90" in data["series"]
        assert len(data["series"]["p50"]) == 6

    def test_custom_percentiles_via_query_param(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=2)
        sim_results = tuple(
            _make_sim_result(
                str(100000), months_simulated=4,
                portfolio_values=[100000 + i * 5000 for i in range(4)],
            )
            for _ in range(2)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(
            f"/persistence/results/{result_id}/trajectory",
            params={"percentiles": "25,75"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["percentiles"] == [25.0, 75.0]
        assert "p25" in data["series"]
        assert "p75" in data["series"]
        assert "p50" not in data["series"]

    def test_invalid_percentile_value_returns_400(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=1)
        sim_results = (_make_sim_result("500000"),)
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(
            f"/persistence/results/{result_id}/trajectory",
            params={"percentiles": "abc"},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "INVALID_PERCENTILES"

    def test_percentile_out_of_range_returns_400(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=1)
        sim_results = (_make_sim_result("500000"),)
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(
            f"/persistence/results/{result_id}/trajectory",
            params={"percentiles": "150"},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "INVALID_PERCENTILES"

    def test_too_many_percentiles_returns_400(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=1)
        sim_results = (_make_sim_result("500000"),)
        result_id = _save_result(repo, plan, sim_results, ctx)

        many = ",".join(str(i) for i in range(25))
        response = client.get(
            f"/persistence/results/{result_id}/trajectory",
            params={"percentiles": many},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["detail"]["error"]["code"] == "INVALID_PERCENTILES"

    def test_empty_percentiles_string_uses_defaults(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=1)
        sim_results = (
            _make_sim_result(
                "500000", months_simulated=3,
                portfolio_values=[100000, 110000, 120000],
            ),
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(
            f"/persistence/results/{result_id}/trajectory",
            params={"percentiles": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["percentiles"] == [10.0, 25.0, 50.0, 75.0, 90.0]

    def test_boundary_percentiles_zero_and_hundred(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=2)
        sim_results = tuple(
            _make_sim_result(
                str(v), months_simulated=3,
                portfolio_values=[v, v, v],
            )
            for v in [100000, 200000]
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(
            f"/persistence/results/{result_id}/trajectory",
            params={"percentiles": "0,100"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["percentiles"] == [0.0, 100.0]
        assert "p0" in data["series"]
        assert "p100" in data["series"]

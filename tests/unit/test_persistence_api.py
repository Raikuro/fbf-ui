"""API tests for persistence endpoints."""

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


class DummySimulationResultCodec:
    def dump(self, result: object) -> object:
        from fbf.core.persistence.studies.sqlite.sqlite_repository import (
            SerializedSimulationResult,
        )
        return SerializedSimulationResult(
            statistics_payload_json="{}",
            monthly_payloads_json=(),
        )

    def load(self, statistics_payload_json: str, monthly_payloads_json: list[str]) -> object:
        return object()


def _make_context() -> PersistenceReconstructionContext:
    return PersistenceReconstructionContext(
        dataset_resolver=DummyDatasetResolver(),
        policy_codecs={
            ("allocation", "AllocationPolicy"): DummyAllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): DummyWithdrawalPolicyCodec(),
        },
        simulation_result_codec=DummySimulationResultCodec(),
    )


def _make_experiment(name: str = "test-exp") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="API test experiment",
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


def _make_plan(num_units: int = 2) -> ResearchPlan:
    experiment = _make_experiment()
    units = tuple(_make_unit(month=((i % 12) + 1)) for i in range(num_units))
    return ResearchPlan(experiment_definition=experiment, units=units)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a test client with a temporary database."""
    db_file = tmp_path / "test_api.db"
    SQLiteRepository(str(db_file))  # Initialize schema

    # Patch the default DB path
    import fbf.ui.api.persistence as persistence_module

    original = persistence_module._DEFAULT_DB_PATH
    persistence_module._DEFAULT_DB_PATH = db_file

    app = __import__("fastapi", fromlist=["FastAPI"]).FastAPI()
    app.include_router(router)
    test_client = TestClient(app)

    yield test_client

    persistence_module._DEFAULT_DB_PATH = original


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    db_file = tmp_path / "test_repo.db"
    return SQLiteRepository(str(db_file))


# ---------------------------------------------------------------------------
# GET /experiments — empty database
# ---------------------------------------------------------------------------


def test_list_experiments_empty(client: TestClient) -> None:
    response = client.get("/persistence/experiments")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /experiments — with data
# ---------------------------------------------------------------------------


def test_list_experiments_with_data(client: TestClient) -> None:
    import fbf.ui.api.persistence as persistence_module

    db_file = persistence_module._DEFAULT_DB_PATH
    repo = SQLiteRepository(str(db_file))
    ctx = _make_context()
    experiment = _make_experiment(name="api-list")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=3)
    repo.save_plan(plan, exp_id, ctx)

    response = client.get("/persistence/experiments")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "api-list"
    assert data[0]["status"] == "pending"
    assert data[0]["unit_count"] == 3


# ---------------------------------------------------------------------------
# GET /experiments/{id} — missing
# ---------------------------------------------------------------------------


def test_get_experiment_missing(client: TestClient) -> None:
    response = client.get("/persistence/experiments/nonexistent-id")
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert body["detail"]["error"]["code"] == "EXPERIMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /experiments/{id} — found
# ---------------------------------------------------------------------------


def test_get_experiment_found(client: TestClient) -> None:
    import fbf.ui.api.persistence as persistence_module

    db_file = persistence_module._DEFAULT_DB_PATH
    repo = SQLiteRepository(str(db_file))
    ctx = _make_context()
    experiment = _make_experiment(name="api-detail")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=2)
    repo.save_plan(plan, exp_id, ctx)

    response = client.get(f"/persistence/experiments/{exp_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "api-detail"
    assert data["description"] == "API test experiment"
    assert len(data["plans"]) == 1
    assert data["plans"][0]["has_results"] is False


# ---------------------------------------------------------------------------
# GET /experiments/{id}/plans — missing experiment
# ---------------------------------------------------------------------------


def test_list_plans_missing_experiment(client: TestClient) -> None:
    response = client.get("/persistence/experiments/nonexistent-id/plans")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /experiments/{id}/plans — found
# ---------------------------------------------------------------------------


def test_list_plans_found(client: TestClient) -> None:
    import fbf.ui.api.persistence as persistence_module

    db_file = persistence_module._DEFAULT_DB_PATH
    repo = SQLiteRepository(str(db_file))
    ctx = _make_context()
    experiment = _make_experiment(name="api-plans")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=2)
    repo.save_plan(plan, exp_id, ctx)

    response = client.get(f"/persistence/experiments/{exp_id}/plans")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["unit_count"] == 2


# ---------------------------------------------------------------------------
# GET /plans/{id}/results — no result
# ---------------------------------------------------------------------------


def test_get_plan_results_no_result(client: TestClient) -> None:
    response = client.get("/persistence/plans/nonexistent-plan/results")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["error"]["code"] == "RESULT_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /plans/{id}/results — with result
# ---------------------------------------------------------------------------


def test_get_plan_results_found(client: TestClient) -> None:
    import fbf.ui.api.persistence as persistence_module

    db_file = persistence_module._DEFAULT_DB_PATH
    repo = SQLiteRepository(str(db_file))
    ctx = _make_context()
    experiment = _make_experiment(name="api-results")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=4)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    sim_contexts = tuple(
        SimulationContext(
            experiment_name=experiment.name,
            cohort=unit.cohort.start_date.isoformat(),
            start_date=unit.cohort.start_date,
            horizon_months=experiment.horizon_months,
            initial_wealth=experiment.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=_TEST_DATASET,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        for unit in plan.units
    )
    engine_def = EngineExperimentDefinition(
        name=experiment.name,
        description=experiment.description,
        simulation_contexts=sim_contexts,
    )
    sim_results = tuple(
        SimulationResult(
            timeline=SimulationTimeline(monthly_results=()),
            statistics=SimulationStatistics(
                final_wealth=Money(Decimal("600000"), Currency.EUR),
                max_drawdown=0.05,
                success=True,
                failure_month=None,
                months_simulated=120,
                execution_time_seconds=0.01,
            ),
        )
        for _ in plan.units
    )
    exp_run = ExperimentRun(definition=engine_def, simulation_results=sim_results)
    result_obj = ResearchExecutionResult(plan=plan, experiment_result=exp_run)
    repo.save_execution_result(plan_id, result_obj, ctx, duration_seconds=2.5)

    response = client.get(f"/persistence/plans/{plan_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == plan_id
    assert data["duration_seconds"] == 2.5
    assert data["total_units"] == 4
    assert "result_id" in data
    assert "success_rate" in data

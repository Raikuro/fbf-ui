"""Unit tests for PersistenceService orchestration layer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
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
    SerializedSimulationResult,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

from fbf.ui.orchestration.persistence_service import (
    ExperimentDetailDTO,
    ExperimentSummaryDTO,
    PersistenceService,
    PlanSummaryDTO,
    ResultSummaryDTO,
    _normalize_plan_status,
)

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
        description="Test experiment for persistence service",
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
def repo(tmp_path: Path) -> SQLiteRepository:
    db_file = tmp_path / "test_persistence.db"
    return SQLiteRepository(str(db_file))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_persistence.db"


@pytest.fixture
def service() -> PersistenceService:
    return PersistenceService()


# ---------------------------------------------------------------------------
# _normalize_plan_status tests
# ---------------------------------------------------------------------------


def test_normalize_plan_status_none() -> None:
    assert _normalize_plan_status(None) == "pending"


def test_normalize_plan_status_planned() -> None:
    assert _normalize_plan_status("planned") == "pending"


def test_normalize_plan_status_completed() -> None:
    assert _normalize_plan_status("completed") == "completed"


def test_normalize_plan_status_failed() -> None:
    assert _normalize_plan_status("failed") == "failed"


def test_normalize_plan_status_executing() -> None:
    assert _normalize_plan_status("executing") == "executing"


# ---------------------------------------------------------------------------
# list_experiments tests
# ---------------------------------------------------------------------------


def test_list_experiments_empty_db(
    service: PersistenceService, db_path: Path
) -> None:
    SQLiteRepository(str(db_path))
    result = service.list_experiments(db_path)
    assert result == []


def test_list_experiments_with_data(
    service: PersistenceService, db_path: Path
) -> None:
    repo = SQLiteRepository(str(db_path))
    ctx = _make_context()
    experiment = _make_experiment(name="svc-test")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=3)
    repo.save_plan(plan, exp_id, ctx)

    result = service.list_experiments(db_path)
    assert len(result) == 1
    dto = result[0]
    assert isinstance(dto, ExperimentSummaryDTO)
    assert dto.name == "svc-test"
    assert dto.status == "pending"
    assert dto.unit_count == 3


def test_list_experiments_status_normalization(
    service: PersistenceService, db_path: Path
) -> None:
    repo = SQLiteRepository(str(db_path))
    ctx = _make_context()
    experiment = _make_experiment(name="norm-test")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=2)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    # Mark as completed
    import sqlite3 as _sqlite3

    with _sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE research_plans SET status = 'completed' WHERE plan_id = ?",
            (plan_id,),
        )

    result = service.list_experiments(db_path)
    assert len(result) == 1
    assert result[0].status == "completed"


# ---------------------------------------------------------------------------
# get_experiment_detail tests
# ---------------------------------------------------------------------------


def test_get_experiment_detail_missing(
    service: PersistenceService, db_path: Path
) -> None:
    SQLiteRepository(str(db_path))
    result = service.get_experiment_detail(db_path, "nonexistent")
    assert result is None


def test_get_experiment_detail_with_plans(
    service: PersistenceService, db_path: Path
) -> None:
    repo = SQLiteRepository(str(db_path))
    ctx = _make_context()
    experiment = _make_experiment(name="detail-test")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=2)
    repo.save_plan(plan, exp_id, ctx)

    detail = service.get_experiment_detail(db_path, exp_id)
    assert detail is not None
    assert isinstance(detail, ExperimentDetailDTO)
    assert detail.name == "detail-test"
    assert detail.description == "Test experiment for persistence service"
    assert len(detail.plans) == 1
    assert isinstance(detail.plans[0], PlanSummaryDTO)
    assert detail.plans[0].has_results is False


def test_get_experiment_detail_has_results(
    service: PersistenceService, db_path: Path
) -> None:
    repo = SQLiteRepository(str(db_path))
    ctx = _make_context()
    experiment = _make_experiment(name="results-test")
    exp_id = repo.save_experiment(
        ExperimentIdentity(name=experiment.name, revision="v1"), experiment, ctx
    )
    plan = _make_plan(num_units=2)
    plan_id = repo.save_plan(plan, exp_id, ctx)

    # Save a result
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
    exp_run = ExperimentRun(
        definition=engine_def,
        simulation_results=sim_results,
    )
    result_obj = ResearchExecutionResult(plan=plan, experiment_result=exp_run)
    repo.save_execution_result(plan_id, result_obj, ctx, duration_seconds=1.0)

    detail = service.get_experiment_detail(db_path, exp_id)
    assert detail is not None
    assert len(detail.plans) == 1
    assert detail.plans[0].has_results is True


# ---------------------------------------------------------------------------
# get_plan_result_summary tests
# ---------------------------------------------------------------------------


def test_get_plan_result_summary_no_result(
    service: PersistenceService, db_path: Path
) -> None:
    SQLiteRepository(str(db_path))
    result = service.get_plan_result_summary(db_path, "nonexistent-plan")
    assert result is None


def test_get_plan_result_summary_with_result(
    service: PersistenceService, db_path: Path
) -> None:
    repo = SQLiteRepository(str(db_path))
    ctx = _make_context()
    experiment = _make_experiment(name="summary-test")
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
    exp_run = ExperimentRun(
        definition=engine_def,
        simulation_results=sim_results,
    )
    result_obj = ResearchExecutionResult(plan=plan, experiment_result=exp_run)
    repo.save_execution_result(plan_id, result_obj, ctx, duration_seconds=3.0)

    summary = service.get_plan_result_summary(db_path, plan_id)
    assert summary is not None
    assert isinstance(summary, ResultSummaryDTO)
    assert summary.plan_id == plan_id
    assert summary.duration_seconds == 3.0
    assert summary.total_units == 4
    assert summary.success_rate > 0

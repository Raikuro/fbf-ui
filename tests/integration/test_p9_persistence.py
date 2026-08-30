"""P9 integration test: real execution → real persistence → P8 discovery.

Uses a small synthetic BuiltStudy and a temporary SQLite database.
All Core persistence APIs are exercised without mocking.
"""

from __future__ import annotations

import resource
import tempfile
import time
from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution import ExecutionOptions, execute_study_plan
from fbf.core.persistence import (
    ExperimentIdentity,
    create_study_repository,
)
from fbf.core.persistence.studies.sqlite.codecs import (
    AllocationPolicyCodec,
    DefaultDatasetResolver,
    SimulationResultCodec,
    WithdrawalPolicyCodec,
)
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    PersistenceReconstructionContext,
)
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

from fbf.ui.orchestration.execution_service import ExecutionService, ExecutionStatus
from fbf.ui.orchestration.persistence_service import PersistenceService

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

_DATASET_IDENTIFIER = "p9_test_dataset"


def _make_persistence_ctx(dataset: Dataset) -> PersistenceReconstructionContext:
    """Create a persistence context with the given dataset registered."""
    resolver = DefaultDatasetResolver(datasets={_DATASET_IDENTIFIER: dataset})
    return PersistenceReconstructionContext(
        dataset_resolver=resolver,
        policy_codecs={
            ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )


def _make_small_dataset(n_months: int = 25) -> Dataset:
    """Create a deterministic synthetic dataset (25 months = ~2 years)."""
    pe = pb = Decimal("100")
    snapshots = []
    d = date(2000, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0.002"),
                inflation_cumulative=Decimal("0"),
                is_ath=(pe >= Decimal("100")),
                is_underwater=(pe < Decimal("100")),
                running_ath=pe,
            )
        )
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(
        snapshots=snapshots,
        frequency="monthly",
        version="1.0",
        identifier=_DATASET_IDENTIFIER,
    )


def _make_built_study() -> BuiltStudy:
    """Build a small BuiltStudy with 2 cohorts × 1 config = 2 units."""
    dataset = _make_small_dataset(25)
    horizon = 12  # 1 year

    cohorts = (
        CohortSpecification(start_date=date(2000, 1, 1)),
        CohortSpecification(start_date=date(2000, 2, 1)),
    )

    policy = ConstantAllocationPolicy(Decimal("0.6"))
    withdrawal = FixedRealWithdrawalPolicy(Decimal("0.04"))
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))

    experiment = ExperimentDefinition(
        name="P9 Integration Test",
        description="Small integration test for P9 persistence",
        dataset=dataset,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(policy,),
        withdrawal_policies=(withdrawal,),
    )

    param_config = ParameterConfiguration({
        "equity_allocation": 0.6,
        "withdrawal_rate": 0.04,
        "horizon_years": 1,
    })

    units = []
    for cohort in cohorts:
        unit = PlannedSimulationUnit(
            cohort=cohort,
            parameter_config=param_config,
            allocation_policy=policy,
            withdrawal_policy=withdrawal,
            initial_portfolio=portfolio,
            dataset=dataset.slice(cohort.start_date, horizon),
        )
        units.append(unit)

    plan = ResearchPlan(experiment_definition=experiment, units=tuple(units))

    return BuiltStudy(
        plan=plan,
        experiment_definition=experiment,
        cohorts=cohorts,
        param_configs=(param_config,),
    )


@pytest.fixture
def tmp_db() -> Generator[Path]:
    """Provide a temporary SQLite database path, cleaned up after test."""
    with tempfile.TemporaryDirectory(prefix="p9_test_") as td:
        yield Path(td) / "test.db"


def _get_peak_rss_mb() -> float:
    """Return peak RSS in MB (Linux/Mac)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss / 1024  # Convert KB to MB on Linux


# ------------------------------------------------------------------
# Integration test: execute → persist → discover
# ------------------------------------------------------------------


def test_p9_execute_persist_discover(tmp_db: Path) -> None:
    """Full round-trip: build study → execute → persist → P8 discovers result."""
    built = _make_built_study()
    n_units = len(built.plan.units)

    # --- Execute ---
    exec_start = time.perf_counter()
    result = execute_study_plan(built, options=ExecutionOptions())
    exec_duration = time.perf_counter() - exec_start

    # --- Persist ---
    ctx = _make_persistence_ctx(built.plan.experiment_definition.dataset)
    repo = create_study_repository(str(tmp_db))

    identity = ExperimentIdentity(
        name=built.experiment_definition.name,
        revision="exec-integration-test",
    )

    persist_start = time.perf_counter()
    experiment_id = repo.save_experiment(
        identity, built.experiment_definition, ctx
    )
    plan_id = repo.save_plan(built.plan, experiment_id, ctx)
    result_id = repo.save_execution_result(plan_id, result, ctx, exec_duration)
    persist_duration = time.perf_counter() - persist_start

    total_duration = time.perf_counter() - exec_start

    # --- Database size ---
    db_size_bytes = tmp_db.stat().st_size

    # --- Memory ---
    peak_rss_mb = _get_peak_rss_mb()

    # --- Simulation result counts ---
    n_simulation_results = len(result.experiment_result.simulation_results)
    success_count = sum(
        1 for r in result.experiment_result.simulation_results if r.statistics.success
    )
    failure_count = n_simulation_results - success_count

    # --- Result size in memory (approximate via pickle) ---
    import pickle
    result_size_bytes = len(pickle.dumps(result))

    # --- P8 Discovery ---
    persistence_svc = PersistenceService()

    # 1. Experiment is discoverable
    experiments = persistence_svc.list_experiments(tmp_db)
    assert len(experiments) >= 1
    exp_summary = experiments[0]
    assert exp_summary.name == "P9 Integration Test"
    assert exp_summary.dataset_identifier is not None

    # 2. Experiment detail with plans
    detail = persistence_svc.get_experiment_detail(tmp_db, experiment_id)
    assert detail is not None
    assert detail.name == "P9 Integration Test"
    assert len(detail.plans) >= 1

    # 3. Plan is marked completed
    plan_summary = detail.plans[0]
    assert plan_summary.status == "completed"
    assert plan_summary.unit_count == n_units

    # 4. has_results=True
    assert plan_summary.has_results is True

    # 5. Result summary is retrievable
    result_summary = persistence_svc.get_plan_result_summary(tmp_db, plan_id)
    assert result_summary is not None
    assert result_summary.result_id == result_id
    assert result_summary.plan_id == plan_id

    # 6. Success/failure counts are correct
    assert result_summary.success_count == success_count
    assert result_summary.failure_count == failure_count
    assert result_summary.total_units == n_units

    # 7. Persisted duration corresponds to execution time (not persistence)
    assert result_summary.duration_seconds is not None
    assert abs(result_summary.duration_seconds - exec_duration) < 0.1

    # --- Print benchmark report ---
    print("\n" + "=" * 60)
    print("P9 INTEGRATION TEST — BENCHMARK REPORT")
    print("=" * 60)
    print(f"  Units executed:              {n_units}")
    print(f"  Simulation results:          {n_simulation_results}")
    print(f"  Success count:               {success_count}")
    print(f"  Failure count:               {failure_count}")
    print(f"  Execution time:              {exec_duration:.4f}s")
    print(f"  Persistence time:            {persist_duration:.4f}s")
    print(f"  Total (exec+persist):        {total_duration:.4f}s")
    print(f"  Result size in memory:       {result_size_bytes:,} bytes"
          f" ({result_size_bytes/1024:.1f} KB)")
    print(f"  SQLite database size:        {db_size_bytes:,} bytes ({db_size_bytes/1024:.1f} KB)")
    print(f"  Peak RSS:                    {peak_rss_mb:.1f} MB")
    print(f"  Persisted duration (stored): {result_summary.duration_seconds:.4f}s")
    print("=" * 60)


# ------------------------------------------------------------------
# DuplicateStudyError idempotency
# ------------------------------------------------------------------


def test_p9_duplicate_persistence_raises(tmp_db: Path) -> None:
    """Persisting the same study twice raises DuplicateStudyError."""
    from fbf.core.persistence import DuplicateStudyError

    built = _make_built_study()
    result = execute_study_plan(built, options=ExecutionOptions())

    ctx = _make_persistence_ctx(built.plan.experiment_definition.dataset)
    repo = create_study_repository(str(tmp_db))
    identity = ExperimentIdentity(
        name=built.experiment_definition.name,
        revision="exec-dup-test",
    )

    experiment_id = repo.save_experiment(
        identity, built.experiment_definition, ctx
    )
    plan_id = repo.save_plan(built.plan, experiment_id, ctx)
    repo.save_execution_result(plan_id, result, ctx, 0.1)

    # Second persist with same identity should raise
    with pytest.raises(DuplicateStudyError):
        repo.save_experiment(
            identity, built.experiment_definition, ctx
        )


# ------------------------------------------------------------------
# ExecutionService integration (thread-based, real persistence)
# ------------------------------------------------------------------


def test_p9_execution_service_persists_to_sqlite(tmp_db: Path) -> None:
    """ExecutionService._run_job persists to real SQLite after execution."""
    built = _make_built_study()
    dataset = built.plan.experiment_definition.dataset

    svc = ExecutionService(max_workers=1, db_path=tmp_db)
    try:
        event = __import__("threading").Event()

        original_execute = execute_study_plan

        def timed_execute(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            event.set()
            return original_execute(*args, **kwargs)

        from unittest.mock import patch

        ctx = _make_persistence_ctx(dataset)

        with (
            patch(
                "fbf.ui.orchestration.execution_service.execute_study_plan",
                side_effect=timed_execute,
            ),
            patch(
                "fbf.ui.orchestration.execution_service.create_persistence_context",
                return_value=ctx,
            ),
        ):
            state = svc.submit_built_study(built)
            event.wait(timeout=10.0)
            time.sleep(0.5)

        final = svc.get_job_state(state.job_id)
        assert final is not None
        assert final.status == ExecutionStatus.COMPLETED
        assert final.error_message is None

        # Verify persistence via P8
        persistence_svc = PersistenceService()
        experiments = persistence_svc.list_experiments(tmp_db)
        assert len(experiments) >= 1
        assert experiments[0].name == "P9 Integration Test"
    finally:
        svc.shutdown(wait=True)

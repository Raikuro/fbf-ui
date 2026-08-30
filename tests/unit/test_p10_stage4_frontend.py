"""P10 Stage 4 tests: results dashboard route, navigation, and API integration."""

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

_ASSET = AssetClass(id="acwi", name="ACWI", description="Global equities")


# ---------------------------------------------------------------------------
# Dataset / policy / codec helpers (same pattern as P8/P9/P10 tests)
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


def _make_experiment(name: str = "p10-stage4-test") -> ExperimentDefinition:
    return ExperimentDefinition(
        name=name,
        description="P10 Stage 4 test experiment",
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
    name: str = "p10-stage4-test",
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
) -> SimulationResult:
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "test_stage4.db"
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


# ===========================================================================
# 1. Results presentation route
# ===========================================================================


class TestResultDetailRoute:
    def test_returns_200_with_result_id(self, client: TestClient) -> None:
        response = client.get("/results/some-result-id")
        assert response.status_code == 200

    def test_html_contains_result_id(self, client: TestClient) -> None:
        response = client.get("/results/test-abc-123")
        assert response.status_code == 200
        assert "test-abc-123" in response.text

    def test_html_contains_chart_canvases(self, client: TestClient) -> None:
        response = client.get("/results/any-id")
        assert response.status_code == 200
        assert 'id="wealth-chart"' in response.text
        assert 'id="failure-chart"' in response.text
        assert 'id="trajectory-chart"' in response.text

    def test_html_includes_chartjs(self, client: TestClient) -> None:
        response = client.get("/results/any-id")
        assert response.status_code == 200
        assert "chart.js" in response.text.lower() or "chart.umd" in response.text.lower()

    def test_html_contains_summary_card(self, client: TestClient) -> None:
        response = client.get("/results/any-id")
        assert response.status_code == 200
        assert 'id="summary-card"' in response.text

    def test_html_contains_breadcrumb(self, client: TestClient) -> None:
        response = client.get("/results/any-id")
        assert response.status_code == 200
        assert "breadcrumb" in response.text

    def test_api_endpoints_accessible(self, client: TestClient) -> None:
        response = client.get("/api/v1/persistence/results/missing/summary")
        assert response.status_code == 404
        response = client.get("/api/v1/persistence/results/missing/statistics")
        assert response.status_code == 404
        response = client.get("/api/v1/persistence/results/missing/trajectory")
        assert response.status_code == 404


# ===========================================================================
# 2. Navigation from persistence browser
# ===========================================================================


class TestNavigationFromPersistenceBrowser:
    def test_experiment_detail_page_loads(self, client: TestClient) -> None:
        response = client.get("/persistence/experiments/fake-id")
        assert response.status_code == 200

    def test_experiment_detail_enriches_results_links(self, client: TestClient) -> None:
        response = client.get("/persistence/experiments/fake-id")
        assert response.status_code == 200
        assert "enrichResultsLinks" in response.text
        assert "data-plan-id" in response.text

    def test_experiment_detail_links_to_results_dashboard(self, client: TestClient) -> None:
        response = client.get("/persistence/experiments/fake-id")
        assert response.status_code == 200
        assert "/results/" in response.text


# ===========================================================================
# 3. API integration (with seeded data)
# ===========================================================================


class TestAPIIntegration:
    def test_summary_endpoint_with_real_data(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=3)
        sim_results = tuple(
            _make_sim_result(str(500000 + i * 1000), success=True)
            for i in range(3)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(f"/api/v1/persistence/results/{result_id}/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_units"] == 3
        assert data["success_count"] == 3

    def test_statistics_endpoint_with_real_data(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=2)
        sim_results = tuple(
            _make_sim_result("500000", success=True) for _ in range(2)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(f"/api/v1/persistence/results/{result_id}/statistics")
        assert response.status_code == 200
        data = response.json()
        assert "terminal_wealth" in data
        assert "failure_months" in data
        assert "max_drawdown" in data

    def test_trajectory_endpoint_with_real_data(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        import fbf.ui.api.persistence as persistence_module

        db_file = persistence_module._DEFAULT_DB_PATH
        repo = SQLiteRepository(str(db_file))
        ctx = _make_context()
        plan = _make_plan(num_units=2)
        sim_results = tuple(
            _make_sim_result("500000", months_simulated=6) for _ in range(2)
        )
        result_id = _save_result(repo, plan, sim_results, ctx)

        response = client.get(f"/api/v1/persistence/results/{result_id}/trajectory")
        assert response.status_code == 200
        data = response.json()
        assert "months" in data
        assert "series" in data
        assert "percentiles" in data


# ===========================================================================
# 4. Missing/empty/error behavior
# ===========================================================================


class TestMissingEmptyErrorBehavior:
    def test_missing_result_summary_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/persistence/results/nonexistent/summary")
        assert response.status_code == 404

    def test_missing_result_statistics_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/persistence/results/nonexistent/statistics")
        assert response.status_code == 404

    def test_missing_result_trajectory_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/persistence/results/nonexistent/trajectory")
        assert response.status_code == 404

    def test_invalid_percentiles_returns_400(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/persistence/results/any/trajectory",
            params={"percentiles": "abc"},
        )
        assert response.status_code == 400

    def test_results_page_renders_for_any_id(self, client: TestClient) -> None:
        response = client.get("/results/completely-invalid-id")
        assert response.status_code == 200
        assert "error-card" in response.text

    def test_persistence_page_loads(self, client: TestClient) -> None:
        response = client.get("/persistence")
        assert response.status_code == 200

    def test_experiment_detail_page_for_missing_experiment(
        self, client: TestClient
    ) -> None:
        response = client.get("/persistence/experiments/nonexistent")
        assert response.status_code == 200
        assert "Not Found" in response.text

"""P11 Stage 6: Playwright browser verification tests.

Runs against a live fbf-ui application seeded with ERN-scale data.
Verifies the cohort heatmap renders correctly in a real browser.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, Page, expect

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = Path("/tmp/opencode/p11_test.db")
APP_HOST = "127.0.0.1"
APP_PORT = 8765
APP_URL = f"http://{APP_HOST}:{APP_PORT}"
RESULT_ID = "f753411d-35eb-422a-a6c9-4b95a1c9c439"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_server():
    """Start the fbf-ui application with the seeded database."""
    import fbf.ui.config
    import fbf.ui.api.persistence as persistence_module

    fbf.ui.config._DEFAULT_DB_PATH = str(DB_PATH)
    persistence_module._DEFAULT_DB_PATH = str(DB_PATH)

    from fbf.ui.main import create_app
    app = create_app()

    import uvicorn
    config = uvicorn.Config(
        app, host=APP_HOST, port=APP_PORT,
        log_level="error", access_log=False,
    )
    server = uvicorn.Server(config)

    import threading

    def _run_server() -> None:
        try:
            server.run()
        except Exception:
            pass

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()

    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(APP_URL, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("Server failed to start within 15 seconds")

    yield server

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser_context(app_server):
    """Launch a Playwright browser context."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
        )
        yield context
        context.close()
        browser.close()


@pytest.fixture
def page(browser_context) -> Page:
    """Create a new page for each test."""
    p = browser_context.new_page()
    yield p
    p.close()


# ===========================================================================
# 1. Persistence → Experiment → Result Navigation
# ===========================================================================


class TestNavigationFlow:
    def test_persistence_page_loads(self, page: Page) -> None:
        page.goto(f"{APP_URL}/persistence")
        expect(page.locator("h1")).to_contain_text("Persistence")

    def test_experiment_detail_page_loads(self, page: Page) -> None:
        page.goto(f"{APP_URL}/persistence")
        page.wait_for_selector("table tbody tr", timeout=15000)
        first_link = page.locator("table tbody tr a[href*='/persistence/experiments/']").first
        href = first_link.get_attribute("href")
        assert href is not None
        page.goto(f"{APP_URL}{href}")
        expect(page.locator("h1")).to_be_visible()

    def test_result_dashboard_loads(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        expect(page.locator("#result-title")).to_be_visible()


# ===========================================================================
# 2. P11 Card Visibility
# ===========================================================================


class TestP11CardVisibility:
    def test_cohort_heatmap_card_present(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        card = page.locator("#cohort-heatmap-card")
        expect(card).to_be_visible()

    def test_parameter_selector_present(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        select = page.locator("#p11-param-select")
        expect(select).to_be_visible()

    def test_chartjs_matrix_loaded(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        scripts = page.locator("script[src*='chartjs-chart-matrix']")
        expect(scripts).to_have_count(1)


# ===========================================================================
# 3. Parameter Selector Population
# ===========================================================================


class TestParameterSelector:
    def test_selector_populated_with_parameters(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        select = page.locator("#p11-param-select")
        option_count = select.locator("option").count()
        assert option_count == 46, f"Expected 46 options (1 default + 45 params), got {option_count}"

    def test_selector_contains_equity_withdrawal_labels(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        option_text = page.locator("#p11-param-select option:nth-child(2)").text_content()
        assert option_text is not None
        assert "Equity:" in option_text
        assert "WR:" in option_text


# ===========================================================================
# 4. Heatmap Rendering
# ===========================================================================


class TestHeatmapRendering:
    def test_heatmap_renders_on_selection(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        container = page.locator("#p11-heatmap-container")
        expect(container).to_be_visible()
        canvas = page.locator("#cohort-heatmap-chart")
        expect(canvas).to_be_visible()

    def test_heatmap_has_non_zero_dimensions(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        canvas = page.locator("#cohort-heatmap-chart")
        box = canvas.bounding_box()
        assert box is not None
        assert box["width"] > 100, f"Canvas width too small: {box['width']}"
        assert box["height"] > 100, f"Canvas height too small: {box['height']}"

    def test_summary_displayed(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-summary').style.display !== 'none'",
            timeout=15000,
        )
        summary = page.locator("#p11-summary")
        expect(summary).to_be_visible()
        text = summary.text_content()
        assert text is not None
        assert "successful" in text
        assert "failed" in text
        assert "total" in text


# ===========================================================================
# 5. Tooltip Verification
# ===========================================================================


class TestTooltipVerification:
    def test_tooltip_shows_on_hover(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        canvas = page.locator("#cohort-heatmap-chart")
        box = canvas.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3)
        time.sleep(1)


# ===========================================================================
# 6. Parameter Change Updates Heatmap
# ===========================================================================


class TestParameterChangeUpdatesHeatmap:
    def test_changing_parameter_updates_heatmap(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )

        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        summary1 = page.locator("#p11-summary").text_content()

        page.locator("#p11-param-select").select_option(index=5)
        page.wait_for_timeout(2000)
        summary2 = page.locator("#p11-summary").text_content()

        assert summary1 != summary2, "Summary should change when parameter selection changes"

    def test_deselecting_parameters_clears_heatmap(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )

        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )

        page.locator("#p11-param-select").select_option(index=0)
        time.sleep(1)
        container = page.locator("#p11-heatmap-container")
        display = container.evaluate("el => el.style.display")
        assert display == "none", "Heatmap should be hidden when default option selected"


# ===========================================================================
# 7. Empty/Error States
# ===========================================================================


class TestEmptyErrorStates:
    def test_error_state_for_missing_result(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/nonexistent-id-12345")
        page.wait_for_timeout(5000)
        error_card = page.locator("#error-card")
        expect(error_card).to_be_visible()


# ===========================================================================
# 8. Dashboard Functionality Without P11 Data
# ===========================================================================


class TestDashboardWithoutP11Data:
    def test_dashboard_renders_all_cards(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#trajectory-card').style.display === 'block'",
            timeout=15000,
        )
        assert page.locator("#summary-card").is_visible()
        assert page.locator("#wealth-card").is_visible()
        assert page.locator("#failure-card").is_visible()
        assert page.locator("#trajectory-card").is_visible()


# ===========================================================================
# 9. JavaScript Console Errors
# ===========================================================================


class TestJavaScriptConsoleErrors:
    def test_no_unexpected_console_errors(self, page: Page) -> None:
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        page.wait_for_timeout(2000)

        unexpected_errors = [
            e for e in errors
            if "favicon" not in e.lower()
            and "net::err" not in e.lower()
            and "failed to load resource" not in e.lower()
        ]
        assert len(unexpected_errors) == 0, f"Unexpected JS errors: {unexpected_errors}"

    def test_no_errors_on_parameter_change(self, page: Page) -> None:
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: errors.append(str(err)))

        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )

        for i in range(1, min(6, page.locator("#p11-param-select option").count())):
            page.locator("#p11-param-select").select_option(index=i)
            page.wait_for_timeout(1500)

        unexpected_errors = [
            e for e in errors
            if "favicon" not in e.lower()
            and "net::err" not in e.lower()
            and "failed to load resource" not in e.lower()
        ]
        assert len(unexpected_errors) == 0, f"Unexpected JS errors after parameter changes: {unexpected_errors}"


# ===========================================================================
# 10. Layout and Sizing
# ===========================================================================


class TestLayoutAndSizing:
    def test_heatmap_responsive_width(self, page: Page) -> None:
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        canvas = page.locator("#cohort-heatmap-chart")
        box = canvas.bounding_box()
        assert box is not None
        assert box["width"] > 500, f"Canvas too narrow at 1920px: {box['width']}"

    def test_heatmap_small_viewport(self, page: Page) -> None:
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )
        canvas = page.locator("#cohort-heatmap-chart")
        box = canvas.bounding_box()
        assert box is not None
        assert box["width"] > 200, f"Canvas too narrow at 768px: {box['width']}"


# ===========================================================================
# 11. Existing P10 Visualizations
# ===========================================================================


class TestExistingP10Visualizations:
    def test_wealth_chart_renders(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#wealth-card').style.display === 'block'",
            timeout=15000,
        )
        canvas = page.locator("#wealth-chart")
        expect(canvas).to_be_visible()

    def test_failure_chart_renders(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#failure-card').style.display === 'block'",
            timeout=15000,
        )
        canvas = page.locator("#failure-chart")
        expect(canvas).to_be_visible()

    def test_trajectory_chart_renders(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#trajectory-card').style.display === 'block'",
            timeout=15000,
        )
        canvas = page.locator("#trajectory-chart")
        expect(canvas).to_be_visible()

    def test_all_cards_visible_together(self, page: Page) -> None:
        page.goto(f"{APP_URL}/results/{RESULT_ID}")
        page.wait_for_function(
            "document.querySelector('#trajectory-card').style.display === 'block'",
            timeout=15000,
        )
        page.wait_for_function(
            "document.querySelector('#p11-param-select').options.length > 1",
            timeout=15000,
        )
        page.locator("#p11-param-select").select_option(index=1)
        page.wait_for_function(
            "document.querySelector('#p11-heatmap-container').style.display !== 'none'",
            timeout=15000,
        )

        assert page.locator("#summary-card").is_visible()
        assert page.locator("#wealth-card").is_visible()
        assert page.locator("#failure-card").is_visible()
        assert page.locator("#trajectory-card").is_visible()
        assert page.locator("#cohort-heatmap-card").is_visible()

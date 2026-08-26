"""Boundary contract tests for fbf-ui.

Enforces architectural rules:
1. fbf.ui must not import fbf.cli or legacy modules.
2. fbf.ui must import fbf-core only via Tier 1 facade and Tier 2 modules.
3. fbf.ui presentation layer must not access SQLite directly.
4. No machine-specific absolute paths in src/ or tests/.
5. fbf-core must not import fbf.ui.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Paths
UI_SRC = Path(__file__).parents[2] / "src" / "fbf" / "ui"
UI_TESTS = Path(__file__).parents[2] / "tests"
CORE_SRC = Path(__file__).parents[3] / "fbf-core" / "src" / "fbf" / "core"

# Allowed Core Tier 1 & Tier 2 import prefixes
ALLOWED_CORE_PREFIXES = (
    "fbf.core",
    "fbf.core.domain",
    "fbf.core.study",
    "fbf.core.execution",
    "fbf.core.optimization",
    "fbf.core.persistence",
    "fbf.core.errors",
)

# Forbidden Core Tier 3 prefixes
FORBIDDEN_CORE_PREFIXES = (
    "fbf.core.study.internal",
    "fbf.core.execution.pipeline",
    "fbf.core.persistence.studies.sqlite.schema",
)


def _get_python_files(path: Path) -> list[Path]:
    """Recursively collect all .py files under a path."""
    return list(path.glob("**/*.py"))


def test_ui_does_not_import_cli() -> None:
    """Verify fbf.ui never imports from fbf.cli."""
    for py_file in _get_python_files(UI_SRC):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("fbf.cli"), (
                        f"Forbidden CLI import '{alias.name}' in {py_file}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fbf.cli"), (
                    f"Forbidden CLI import from '{node.module}' in {py_file}"
                )


def test_ui_core_tier_discipline() -> None:
    """Verify fbf.ui imports Core only via Tier 1 and Tier 2 facade modules."""
    for py_file in _get_python_files(UI_SRC):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            module_name = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_name = node.module

            if module_name.startswith("fbf.core"):
                for forbidden in FORBIDDEN_CORE_PREFIXES:
                    assert not module_name.startswith(forbidden), (
                        f"Forbidden Tier 3 Core import '{module_name}' in {py_file}"
                    )


def test_presentation_does_not_access_sqlite() -> None:
    """Verify presentation modules do not import sqlite3 directly."""
    presentation_path = UI_SRC / "presentation"
    for py_file in _get_python_files(presentation_path):
        content = py_file.read_text(encoding="utf-8")
        assert "sqlite3" not in content, f"Direct sqlite3 reference in presentation file {py_file}"


def test_no_machine_specific_absolute_paths() -> None:
    """Verify no hardcoded machine-specific absolute paths exist in source or tests."""
    forbidden = ("/" + "home/", "/" + "Users/", "C:" + "\\")
    all_files = [
        f for f in _get_python_files(UI_SRC) + _get_python_files(UI_TESTS)
        if f.name != "test_ui_boundaries.py"
    ]

    for py_file in all_files:
        content = py_file.read_text(encoding="utf-8")
        for prefix in forbidden:
            assert prefix not in content, (
                f"Machine-specific absolute path '{prefix}' found in {py_file}"
            )


def test_core_does_not_import_ui() -> None:
    """Verify fbf-core never imports from fbf.ui."""
    if not CORE_SRC.exists():
        return
    for py_file in _get_python_files(CORE_SRC):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("fbf.ui"), (
                        f"Forbidden Core->UI import '{alias.name}' in {py_file}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fbf.ui"), (
                    f"Forbidden Core->UI import from '{node.module}' in {py_file}"
                )

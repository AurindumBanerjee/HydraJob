"""Unit tests for timezone formatting, UI components, theme, and strict separation rules."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from components.status_badge import format_status_badge_html, get_status_presentation
from components.theme import PALETTE, get_theme_css
from components.widgets import format_csv_list, parse_csv_list
from services.time_utils import format_kolkata_timestamp, now_kolkata_formatted


def test_format_kolkata_timestamp_converts_utc_iso_to_ist() -> None:
    formatted = format_kolkata_timestamp("2026-11-14T10:30:00Z")
    assert formatted == "2026-11-14 16:00:00 IST"


def test_format_kolkata_timestamp_handles_naive_datetime_and_edge_cases() -> None:
    naive = datetime(2026, 1, 15, 0, 0, 0)
    assert format_kolkata_timestamp(naive) == "2026-01-15 05:30:00 IST"

    aware = datetime(2026, 1, 15, 0, 0, 0, tzinfo=UTC)
    assert format_kolkata_timestamp(aware) == "2026-01-15 05:30:00 IST"

    assert format_kolkata_timestamp(None) == "Unavailable"
    assert format_kolkata_timestamp("   ") == "Unavailable"
    assert format_kolkata_timestamp("not-a-timestamp") == "not-a-timestamp"
    assert now_kolkata_formatted().endswith("IST")


def test_status_badge_presentation_and_xss_escaping() -> None:
    assert get_status_presentation("healthy").label == "Healthy"
    assert get_status_presentation("degraded").label == "Degraded"
    assert get_status_presentation("unavailable").label == "Unavailable"
    assert get_status_presentation("ELIGIBLE").label == "Healthy"
    assert get_status_presentation("INELIGIBLE").label == "Unavailable"
    assert get_status_presentation("NEEDS_CONFIGURATION").label == "Degraded"
    assert get_status_presentation("APPLIED").label == "Info"
    assert get_status_presentation("other").label == "Unknown"

    badge = format_status_badge_html("healthy", label_override="<script>alert(1)</script>")
    assert "<script>" not in badge
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in badge


def test_csv_list_helpers() -> None:
    assert parse_csv_list("Python, PyTorch , , SQL ") == ["Python", "PyTorch", "SQL"]
    assert parse_csv_list("   ") == []
    assert format_csv_list(["Python", "SQL"]) == "Python, SQL"
    assert format_csv_list(None) == ""


def test_editorial_theme_palette_and_no_external_fonts() -> None:
    css = get_theme_css()
    assert PALETTE["paper"] == "#FBFAF6"
    assert PALETTE["paper_warm"] == "#F3EFE5"
    assert PALETTE["accent"] == "#7A2E3B"
    assert PALETTE["blueprint"] == "#1F4A5C"
    assert PALETTE["sage"] == "#4E6A56"
    assert PALETTE["amber"] == "#B47A28"
    assert "fonts.googleapis.com" not in css.lower()
    assert "fonts.gstatic.com" not in css.lower()
    assert "fraunces" not in css.lower()
    assert "jetbrains" not in css.lower()


def test_dashboard_has_no_direct_database_imports_and_valid_syntax() -> None:
    dashboard_root = Path(__file__).resolve().parent.parent
    forbidden_modules = {"sqlalchemy", "psycopg", "psycopg2", "asyncpg", "sqlite3"}

    py_files = list(dashboard_root.rglob("*.py"))
    assert py_files, "Expected Python files inside dashboard/"

    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8")
        if "tests" not in py_file.relative_to(dashboard_root).parts:
            assert "fonts.googleapis.com" not in source.lower(), (
                f"External Google Fonts reference found in {py_file}"
            )
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    assert top_level not in forbidden_modules, (
                        f"Forbidden DB import {top_level!r} in {py_file}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level = node.module.split(".")[0]
                assert top_level not in forbidden_modules, (
                    f"Forbidden DB import {top_level!r} in {py_file}"
                )

"""Tests for browser export partial offload (HA-08)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from busybee_cpu.browser_export import (
    BrowserExportTracker,
    ExportFormat,
    ExportSpec,
    ExportStep,
    ValidationResult,
    parse_export_spec,
    validate_export_artifact,
)
from busybee_cpu.resolver import resolve_action_args


# ---------------------------------------------------------------------------
# ExportSpec
# ---------------------------------------------------------------------------


class TestExportSpec:
    def test_to_dict(self) -> None:
        spec = ExportSpec(
            url="https://example.com/export",
            format=ExportFormat.CSV,
            requires_login=True,
            login_url="https://example.com/login",
        )
        data = spec.to_dict()
        assert data["url"] == "https://example.com/export"
        assert data["format"] == "csv"
        assert data["requires_login"] is True
        assert data["login_url"] == "https://example.com/login"

    def test_from_dict(self) -> None:
        data = {
            "url": "https://example.com/export",
            "format": "json",
            "requires_login": False,
            "content_markers": ["id", "name"],
        }
        spec = ExportSpec.from_dict(data)
        assert spec.url == "https://example.com/export"
        assert spec.format == ExportFormat.JSON
        assert spec.requires_login is False
        assert spec.content_markers == ["id", "name"]

    def test_from_dict_unknown_format(self) -> None:
        spec = ExportSpec.from_dict({"format": "parquet"})
        assert spec.format == ExportFormat.UNKNOWN

    def test_roundtrip(self) -> None:
        original = ExportSpec(
            url="https://example.com",
            format=ExportFormat.PDF,
            requires_login=True,
            login_url="https://example.com/login",
            login_credentials_key="sso",
            export_button_selector="aria/Export",
            export_page_url="https://example.com/reports",
            expected_filename_pattern=r".*\.pdf$",
            content_markers=["header", "footer"],
            min_size_bytes=100,
            max_size_bytes=1024,
            verification_steps=["confirm_login", "confirm_download"],
        )
        restored = ExportSpec.from_dict(original.to_dict())
        assert restored.url == original.url
        assert restored.format == original.format
        assert restored.requires_login == original.requires_login
        assert restored.login_url == original.login_url
        assert restored.export_button_selector == original.export_button_selector
        assert restored.content_markers == original.content_markers
        assert restored.verification_steps == original.verification_steps


# ---------------------------------------------------------------------------
# parse_export_spec
# ---------------------------------------------------------------------------


class TestParseExportSpec:
    def test_empty_state_returns_none(self) -> None:
        assert parse_export_spec({}) is None

    def test_no_export_signals_returns_none(self) -> None:
        state = {"recent_observations": ["Just a normal observation."]}
        assert parse_export_spec(state) is None

    def test_extracts_url(self) -> None:
        state = {
            "recent_observations": [
                "Navigate to https://example.com/reports/export to download the data."
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert "example.com" in spec.url

    def test_detects_csv_format(self) -> None:
        state = {
            "recent_observations": [
                "Export the data as CSV from https://example.com/export"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.format == ExportFormat.CSV

    def test_detects_json_format(self) -> None:
        state = {
            "recent_observations": [
                "Download the JSON format report from https://example.com/api/export"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.format == ExportFormat.JSON

    def test_detects_pdf_format(self) -> None:
        state = {
            "recent_observations": [
                "Export as PDF from https://reports.example.com/download"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.format == ExportFormat.PDF

    def test_detects_login_requirement(self) -> None:
        state = {
            "recent_observations": [
                "Login required at https://example.com/login",
                "Then navigate to https://example.com/export"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.requires_login is True
        assert "login" in spec.login_url

    def test_detects_authentication_keyword(self) -> None:
        state = {
            "recent_observations": [
                "Requires authentication via SSO.",
                "Export page: https://secure.example.com/export"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.requires_login is True

    def test_extracts_button_selector(self) -> None:
        state = {
            "recent_observations": [
                "Click button: 'Download Report' on https://example.com/export"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.export_button_selector

    def test_extracts_content_markers_from_features(self) -> None:
        state = {
            "recent_observations": ["Export from https://example.com/export"],
            "policy_features": {"content_markers": ["date", "amount", "customer"]},
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.content_markers == ["date", "amount", "customer"]

    def test_generates_verification_steps(self) -> None:
        state = {
            "recent_observations": [
                "Login required at https://example.com/auth",
                "Navigate to https://example.com/export",
                "Format: csv"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert len(spec.verification_steps) > 0
        assert "confirm_login_success" in spec.verification_steps
        assert "confirm_export_downloaded" in spec.verification_steps
        assert "confirm_csv_format" in spec.verification_steps

    def test_classifies_login_url(self) -> None:
        state = {
            "recent_observations": [
                "Login URL: https://example.com/signin",
                "Export URL: https://example.com/reports/export",
                "Requires authentication."
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert "signin" in spec.login_url
        assert spec.requires_login is True

    def test_extracts_filename_pattern(self) -> None:
        state = {
            "recent_observations": [
                "Export from https://example.com/export",
                "Expected filename: quarterly_report.csv"
            ]
        }
        spec = parse_export_spec(state)
        assert spec is not None
        assert spec.expected_filename_pattern

    def test_export_keyword_only(self) -> None:
        state = {
            "recent_observations": ["The user wants to export the data."]
        }
        spec = parse_export_spec(state)
        assert spec is not None

    def test_download_keyword_only(self) -> None:
        state = {
            "recent_observations": ["Download the latest report."]
        }
        spec = parse_export_spec(state)
        assert spec is not None


# ---------------------------------------------------------------------------
# validate_export_artifact
# ---------------------------------------------------------------------------


class TestValidateExportArtifact:
    def test_missing_file(self) -> None:
        spec = ExportSpec()
        result = validate_export_artifact(spec, "/nonexistent/file.csv")
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_valid_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "report.csv"
        csv_file.write_text("id,name,value\n1,test,100\n2,foo,200\n")
        spec = ExportSpec(format=ExportFormat.CSV, min_size_bytes=1)
        result = validate_export_artifact(spec, csv_file)
        assert result.valid is True
        assert result.format_matched is True

    def test_valid_json(self, tmp_path: Path) -> None:
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps({"key": "value", "count": 42}))
        spec = ExportSpec(format=ExportFormat.JSON, min_size_bytes=1)
        result = validate_export_artifact(spec, json_file)
        assert result.valid is True

    def test_invalid_json(self, tmp_path: Path) -> None:
        json_file = tmp_path / "bad.json"
        json_file.write_text("{invalid json content")
        spec = ExportSpec(format=ExportFormat.JSON)
        result = validate_export_artifact(spec, json_file)
        assert result.valid is False
        assert any("JSON" in e for e in result.errors)

    def test_empty_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        spec = ExportSpec(format=ExportFormat.CSV)
        result = validate_export_artifact(spec, csv_file)
        assert result.valid is False
        assert any("empty" in e for e in result.errors)

    def test_file_too_small(self, tmp_path: Path) -> None:
        small_file = tmp_path / "small.csv"
        small_file.write_text("x")
        spec = ExportSpec(format=ExportFormat.CSV, min_size_bytes=1000)
        result = validate_export_artifact(spec, small_file)
        assert result.valid is False
        assert any("too small" in e for e in result.errors)

    def test_file_too_large(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big.csv"
        big_file.write_text("x" * 1000)
        spec = ExportSpec(format=ExportFormat.CSV, max_size_bytes=100)
        result = validate_export_artifact(spec, big_file)
        assert result.valid is False
        assert any("too large" in e for e in result.errors)

    def test_filename_pattern_match(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "quarterly_report.csv"
        csv_file.write_text("a,b\n1,2\n")
        spec = ExportSpec(
            format=ExportFormat.CSV,
            expected_filename_pattern=r"quarterly.*\.csv$",
        )
        result = validate_export_artifact(spec, csv_file)
        assert result.valid is True

    def test_filename_pattern_mismatch(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "random_data.csv"
        csv_file.write_text("a,b\n1,2\n")
        spec = ExportSpec(
            format=ExportFormat.CSV,
            expected_filename_pattern=r"quarterly.*\.csv$",
        )
        result = validate_export_artifact(spec, csv_file)
        assert result.valid is False
        assert any("Filename" in e for e in result.errors)

    def test_content_markers_found(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "report.csv"
        csv_file.write_text("date,amount,customer\n2024-01-01,100,Acme\n")
        spec = ExportSpec(
            format=ExportFormat.CSV,
            content_markers=["date", "amount", "customer"],
        )
        result = validate_export_artifact(spec, csv_file)
        assert result.valid is True
        assert result.content_markers_found == 3
        assert result.content_markers_total == 3

    def test_content_markers_missing(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "report.csv"
        csv_file.write_text("date,amount\n2024-01-01,100\n")
        spec = ExportSpec(
            format=ExportFormat.CSV,
            content_markers=["date", "amount", "customer"],
        )
        result = validate_export_artifact(spec, csv_file)
        assert result.valid is False
        assert result.content_markers_found == 2
        assert result.content_markers_total == 3

    def test_format_mismatch(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "report.txt"
        txt_file.write_text("some text content")
        spec = ExportSpec(format=ExportFormat.CSV)
        result = validate_export_artifact(spec, txt_file)
        assert result.valid is False
        assert any("format" in e.lower() for e in result.errors)

    def test_valid_html(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<!DOCTYPE html><html><body>Report</body></html>")
        spec = ExportSpec(format=ExportFormat.HTML)
        result = validate_export_artifact(spec, html_file)
        assert result.valid is True

    def test_invalid_html(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("This is not HTML at all")
        spec = ExportSpec(format=ExportFormat.HTML)
        result = validate_export_artifact(spec, html_file)
        assert result.valid is False
        assert any("doctype" in e.lower() or "html" in e.lower() for e in result.errors)

    def test_unknown_format_skips_format_check(self, tmp_path: Path) -> None:
        data_file = tmp_path / "report.dat"
        data_file.write_text("some binary-like content here")
        spec = ExportSpec(format=ExportFormat.UNKNOWN)
        result = validate_export_artifact(spec, data_file)
        assert result.valid is True


# ---------------------------------------------------------------------------
# BrowserExportTracker
# ---------------------------------------------------------------------------


class TestBrowserExportTracker:
    def test_start_returns_init(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com")
        step = tracker.start("session-1", spec)
        assert step == ExportStep.INIT

    def test_current_step(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com")
        tracker.start("session-1", spec)
        assert tracker.current_step("session-1") == ExportStep.INIT

    def test_current_step_unknown_session(self) -> None:
        tracker = BrowserExportTracker()
        assert tracker.current_step("nonexistent") is None

    def test_advance_through_steps(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com", requires_login=False)
        tracker.start("session-1", spec)

        # INIT -> NAVIGATE
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.NAVIGATE

        # NAVIGATE -> EXPORT_PAGE (skip LOGIN since not required)
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.EXPORT_PAGE

        # EXPORT_PAGE -> TRIGGER_EXPORT
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.TRIGGER_EXPORT

        # TRIGGER_EXPORT -> WAIT_DOWNLOAD
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.WAIT_DOWNLOAD

        # WAIT_DOWNLOAD -> VALIDATE
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.VALIDATE

        # VALIDATE -> COMPLETE
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.COMPLETE

    def test_advance_with_login_required(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(
            url="https://example.com/export",
            requires_login=True,
            login_url="https://example.com/login",
        )
        tracker.start("session-1", spec)

        # INIT -> NAVIGATE
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.NAVIGATE

        # NAVIGATE -> LOGIN (login is required)
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.LOGIN

        # LOGIN -> EXPORT_PAGE
        step = tracker.advance("session-1", success=True)
        assert step == ExportStep.EXPORT_PAGE

    def test_advance_failure(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com")
        tracker.start("session-1", spec)
        tracker.advance("session-1", success=True)  # INIT -> NAVIGATE

        step = tracker.advance("session-1", success=False, error="Page not found")
        assert step == ExportStep.FAILED

    def test_is_complete_after_failure(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com")
        tracker.start("session-1", spec)
        tracker.advance("session-1", success=False, error="Network error")
        assert tracker.is_complete("session-1") is True

    def test_is_complete_after_success(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com", requires_login=False)
        tracker.start("session-1", spec)
        # Advance through all steps
        for _ in range(10):
            step = tracker.advance("session-1", success=True)
            if step == ExportStep.COMPLETE:
                break
        assert tracker.is_complete("session-1") is True

    def test_status(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com")
        tracker.start("session-1", spec)
        status = tracker.status("session-1")
        assert status is not None
        assert status["step"] == "init"
        assert status["step_index"] == 0
        assert status["total_steps"] == len([ExportStep.INIT, ExportStep.NAVIGATE, ExportStep.LOGIN, ExportStep.EXPORT_PAGE, ExportStep.TRIGGER_EXPORT, ExportStep.WAIT_DOWNLOAD, ExportStep.VALIDATE, ExportStep.COMPLETE])

    def test_status_unknown_session(self) -> None:
        tracker = BrowserExportTracker()
        assert tracker.status("nonexistent") is None

    def test_cleanup(self) -> None:
        tracker = BrowserExportTracker(ttl_seconds=1)
        spec = ExportSpec(url="https://example.com")
        tracker.start("session-1", spec)
        tracker.start("session-2", spec)
        # Manually expire sessions by setting started time in the past
        for session in tracker._sessions.values():
            session["started"] -= 10  # 10 seconds ago
        removed = tracker.cleanup()
        assert removed == 2
        assert tracker.session_count == 0

    def test_session_count(self) -> None:
        tracker = BrowserExportTracker()
        spec = ExportSpec(url="https://example.com")
        tracker.start("session-1", spec)
        tracker.start("session-2", spec)
        assert tracker.session_count == 2

    def test_advance_unknown_session(self) -> None:
        tracker = BrowserExportTracker()
        assert tracker.advance("nonexistent", success=True) is None


# ---------------------------------------------------------------------------
# Resolver integration
# ---------------------------------------------------------------------------


class TestBrowserResolver:
    def test_resolve_browser_navigate(self) -> None:
        action = {"tool": "browser_navigate", "args": {"url": "<URL_FROM_STATE>"}}
        row = {
            "goal": "Navigate to the export page.",
            "state": {
                "recent_observations": [
                    "Export page URL: https://example.com/reports/export"
                ]
            },
        }
        result = resolve_action_args(action, row)
        assert result["args"]["url"] == "https://example.com/reports/export"

    def test_resolve_browser_click(self) -> None:
        action = {"tool": "browser_click", "args": {"selector": "<SELECTOR_FROM_STATE>"}}
        row = {
            "goal": "Click the export button.",
            "state": {
                "recent_observations": [
                    "Button selector: aria/Download CSV",
                    "Export from https://example.com/export"
                ]
            },
        }
        result = resolve_action_args(action, row)
        assert "selector" in result["args"]
        assert result["args"]["selector"]

    def test_resolve_browser_export(self) -> None:
        action = {"tool": "browser_export", "args": {"spec": {}}}
        row = {
            "goal": "Export the report as CSV.",
            "state": {
                "recent_observations": [
                    "Navigate to https://example.com/export",
                    "Format: csv",
                    "Button: aria/Download"
                ]
            },
        }
        result = resolve_action_args(action, row)
        assert "spec" in result["args"]
        spec = result["args"]["spec"]
        assert isinstance(spec, dict)
        assert "url" in spec
        assert "format" in spec

    def test_resolve_browser_no_signals(self) -> None:
        action = {"tool": "browser_navigate", "args": {"url": "<URL_FROM_STATE>"}}
        row = {
            "goal": "Do something unrelated.",
            "state": {"recent_observations": ["Just a normal message."]},
        }
        result = resolve_action_args(action, row)
        # Should still have the placeholder since no export signals found
        assert result["args"].get("url") == "<URL_FROM_STATE>"

    def test_resolve_browser_navigate_prefers_export_url(self) -> None:
        action = {"tool": "browser_navigate", "args": {"url": "<URL_FROM_STATE>"}}
        row = {
            "goal": "Navigate to the export page.",
            "state": {
                "recent_observations": [
                    "Login URL: https://example.com/login",
                    "Export URL: https://example.com/reports/export",
                    "Requires authentication."
                ]
            },
        }
        result = resolve_action_args(action, row)
        url = result["args"]["url"]
        # Should prefer the export URL over login URL
        assert "export" in url or "reports" in url


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict(self) -> None:
        result = ValidationResult(
            valid=True,
            errors=[],
            file_size=1024,
            format_matched=True,
            content_markers_found=3,
            content_markers_total=3,
        )
        data = result.to_dict()
        assert data["valid"] is True
        assert data["file_size"] == 1024
        assert data["format_matched"] is True
        assert data["content_markers_found"] == 3

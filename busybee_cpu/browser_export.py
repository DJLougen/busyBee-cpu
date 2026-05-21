"""Browser export partial offload for HA-08 scenario.

Provides deterministic helpers that extract structured browser export
specifications from state, validate exported artifacts, and track the
multi-step browser workflow (navigate -> login -> export -> verify).

The CPU adapter does NOT execute browser automation.  It generates a
structured ``ExportSpec`` that the Hermes browser controller consumes,
and validates the resulting artifact against expected format and content.

Typical flow:
    1. ``parse_export_spec(state)`` extracts URL, format, auth, and
       verification criteria from observations and policy_features.
    2. Hermes browser controller executes login, navigation, and DOM
       interaction using the spec.
    3. ``validate_export_artifact(spec, path)`` confirms the exported
       file exists, matches the expected format, and contains required
       content markers.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# export specification
# ---------------------------------------------------------------------------


class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"
    XLSX = "xlsx"
    HTML = "html"
    XML = "xml"
    UNKNOWN = "unknown"


@dataclass
class ExportSpec:
    """Structured specification for a browser export task.

    Generated deterministically from state so the browser controller can
    execute login, navigation, and export without re-planning.
    """

    url: str = ""
    format: ExportFormat = ExportFormat.UNKNOWN
    requires_login: bool = False
    login_url: str = ""
    login_credentials_key: str = ""
    export_button_selector: str = ""
    export_page_url: str = ""
    expected_filename_pattern: str = ""
    content_markers: list[str] = field(default_factory=list)
    min_size_bytes: int = 1
    max_size_bytes: int = 100 * 1024 * 1024  # 100 MiB
    verification_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["format"] = self.format.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExportSpec":
        fmt = data.get("format", "unknown")
        try:
            fmt = ExportFormat(fmt)
        except ValueError:
            fmt = ExportFormat.UNKNOWN
        return cls(
            url=str(data.get("url") or ""),
            format=fmt,
            requires_login=bool(data.get("requires_login")),
            login_url=str(data.get("login_url") or ""),
            login_credentials_key=str(data.get("login_credentials_key") or ""),
            export_button_selector=str(data.get("export_button_selector") or ""),
            export_page_url=str(data.get("export_page_url") or ""),
            expected_filename_pattern=str(data.get("expected_filename_pattern") or ""),
            content_markers=list(data.get("content_markers") or []),
            min_size_bytes=int(data.get("min_size_bytes") or 1),
            max_size_bytes=int(data.get("max_size_bytes") or 100 * 1024 * 1024),
            verification_steps=list(data.get("verification_steps") or []),
        )


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s\"'<>\]\)]+", re.IGNORECASE)
LOGIN_KEYWORDS = frozenset({"login", "signin", "sign-in", "auth", "sso", "oauth"})
EXPORT_KEYWORDS = frozenset({"export", "download", "report", "dump", "extract"})
FORMAT_MAP: dict[str, ExportFormat] = {
    "csv": ExportFormat.CSV,
    "json": ExportFormat.JSON,
    "pdf": ExportFormat.PDF,
    "xlsx": ExportFormat.XLSX,
    "xls": ExportFormat.XLSX,
    "html": ExportFormat.HTML,
    "htm": ExportFormat.HTML,
    "xml": ExportFormat.XML,
}


def _extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def _detect_format(text: str) -> ExportFormat:
    low = text.lower()
    for ext, fmt in FORMAT_MAP.items():
        if f".{ext}" in low or f"{ext} format" in low or f"as {ext}" in low:
            return fmt
    # Check for "Format: <ext>" pattern
    match = re.search(r"format[:\s]+(\w+)", low)
    if match:
        candidate = match.group(1).strip()
        if candidate in FORMAT_MAP:
            return FORMAT_MAP[candidate]
    return ExportFormat.UNKNOWN


def _has_login_requirement(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in LOGIN_KEYWORDS) or "requires authentication" in low


def _extract_selector(text: str) -> str:
    """Extract a CSS or aria selector hint from observation text."""
    patterns = [
        r'selector["\s:=]+([\'"][^\'"]+[\'"])',
        r'button["\s:]+[\'"]([^\'"]+)[\'"]',
        r'aria[/\-]label["\s:=]+[\'"]([^\'"]+)[\'"]',
        r'(aria/[A-Za-z][\w\- ]*)',
        r'click["\s:]+[\'"]([^\'"]+)[\'"]',
        r'Button["\s:]+([A-Za-z][\w\- /]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip("'\"")
            # Remove trailing words like "button", "on", "to"
            value = re.sub(r'\s+(button|on|to|in|for)\b.*$', '', value, flags=re.IGNORECASE).strip()
            if value:
                return value
    return ""


# ---------------------------------------------------------------------------
# state -> ExportSpec
# ---------------------------------------------------------------------------


def parse_export_spec(state: dict[str, Any]) -> ExportSpec | None:
    """Extract a structured export specification from state.

    Scans ``recent_observations`` and ``policy_features`` for URLs, format
    hints, authentication requirements, and export button selectors.

    Returns ``None`` when no export-relevant signals are found.
    """
    observations = state.get("recent_observations") or []
    text = "\n".join(str(item) for item in observations)
    features = state.get("policy_features") or {}
    if isinstance(features, dict):
        text += "\n" + json.dumps(features, ensure_ascii=False)

    if not text.strip():
        return None

    urls = _extract_urls(text)
    if not urls and "export" not in text.lower() and "download" not in text.lower():
        return None

    export_format = _detect_format(text)
    requires_login = _has_login_requirement(text)
    login_url = ""
    export_page_url = ""

    # Classify URLs: login vs export vs navigation
    for url in urls:
        low_url = url.lower()
        if any(kw in low_url for kw in LOGIN_KEYWORDS) and not login_url:
            login_url = url
        elif any(kw in low_url for kw in EXPORT_KEYWORDS) and not export_page_url:
            export_page_url = url

    # Primary URL is the first non-login URL if no export URL found
    primary_url = ""
    for url in urls:
        if url != login_url:
            primary_url = url
            break

    selector = _extract_selector(text)

    # Build verification steps based on what we know
    verification_steps: list[str] = []
    if requires_login:
        verification_steps.append("confirm_login_success")
    if export_page_url or primary_url:
        verification_steps.append("confirm_page_loaded")
    if selector:
        verification_steps.append("confirm_button_visible")
    verification_steps.append("confirm_export_downloaded")
    if export_format != ExportFormat.UNKNOWN:
        verification_steps.append(f"confirm_{export_format.value}_format")

    # Content markers from policy_features
    content_markers: list[str] = []
    if isinstance(features, dict):
        markers = features.get("content_markers") or features.get("expected_content") or []
        if isinstance(markers, list):
            content_markers = [str(m) for m in markers if str(m).strip()]

    # Filename pattern
    filename_pattern = ""
    if export_format != ExportFormat.UNKNOWN:
        filename_pattern = f".*\\.{export_format.value}$"
    match = re.search(r'filename["\s:=]+[\'"]?([^\'"\n]+)[\'"]?', text, re.IGNORECASE)
    if match:
        filename_pattern = re.escape(match.group(1).strip())

    spec = ExportSpec(
        url=primary_url or (urls[0] if urls else ""),
        format=export_format,
        requires_login=requires_login,
        login_url=login_url,
        export_button_selector=selector,
        export_page_url=export_page_url,
        expected_filename_pattern=filename_pattern,
        content_markers=content_markers,
        verification_steps=verification_steps,
    )
    return spec


# ---------------------------------------------------------------------------
# artifact validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of validating an exported artifact."""

    valid: bool = False
    errors: list[str] = field(default_factory=list)
    file_size: int = 0
    format_matched: bool = False
    content_markers_found: int = 0
    content_markers_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_export_artifact(spec: ExportSpec, artifact_path: str | Path) -> ValidationResult:
    """Validate an exported artifact against the export specification.

    Checks:
    - File exists and is within size bounds
    - Filename matches expected pattern
    - Format-specific content validation (CSV headers, JSON parse, etc.)
    - Content markers are present

    Args:
        spec: The export specification to validate against.
        artifact_path: Path to the exported file.

    Returns:
        ``ValidationResult`` with ``valid=True`` when all checks pass.
    """
    path = Path(artifact_path)
    result = ValidationResult()
    errors: list[str] = []

    if not path.exists():
        errors.append(f"Artifact not found: {path}")
        result.errors = errors
        return result

    size = path.stat().st_size
    result.file_size = size

    if size < spec.min_size_bytes:
        errors.append(f"File too small: {size} < {spec.min_size_bytes}")
    if size > spec.max_size_bytes:
        errors.append(f"File too large: {size} > {spec.max_size_bytes}")

    # Filename pattern
    if spec.expected_filename_pattern:
        if not re.search(spec.expected_filename_pattern, path.name, re.IGNORECASE):
            errors.append(f"Filename '{path.name}' does not match pattern '{spec.expected_filename_pattern}'")

    # Format-specific validation
    fmt = spec.format
    if fmt != ExportFormat.UNKNOWN:
        result.format_matched = path.suffix.lower().lstrip(".") in {fmt.value, *{k for k, v in FORMAT_MAP.items() if v == fmt}}
        if not result.format_matched:
            errors.append(f"Expected .{fmt.value} format, got '{path.suffix}'")

        if fmt == ExportFormat.JSON and path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                json.loads(content)
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"JSON parse failed: {exc}")

        elif fmt == ExportFormat.CSV and path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    errors.append("CSV file is empty")
                elif "\n" not in content and "," not in content:
                    errors.append("CSV file has no rows or columns")
            except OSError as exc:
                errors.append(f"CSV read failed: {exc}")

        elif fmt == ExportFormat.HTML and path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if "<html" not in content.lower() and "<!doctype" not in content.lower():
                    errors.append("HTML file missing doctype or html tag")
            except OSError as exc:
                errors.append(f"HTML read failed: {exc}")

        elif fmt == ExportFormat.XML and path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if "<" not in content:
                    errors.append("XML file contains no markup")
            except OSError as exc:
                errors.append(f"XML read failed: {exc}")

    # Content markers
    result.content_markers_total = len(spec.content_markers)
    if spec.content_markers and path.exists():
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            found = sum(1 for marker in spec.content_markers if marker in content)
            result.content_markers_found = found
            if found < len(spec.content_markers):
                missing = [m for m in spec.content_markers if m not in content]
                errors.append(f"Missing content markers: {missing}")
        except OSError:
            errors.append("Could not read file for content marker check")

    result.errors = errors
    result.valid = not errors
    return result


# ---------------------------------------------------------------------------
# multi-step export tracker
# ---------------------------------------------------------------------------


class ExportStep(str, Enum):
    INIT = "init"
    NAVIGATE = "navigate"
    LOGIN = "login"
    EXPORT_PAGE = "export_page"
    TRIGGER_EXPORT = "trigger_export"
    WAIT_DOWNLOAD = "wait_download"
    VALIDATE = "validate"
    COMPLETE = "complete"
    FAILED = "failed"


_STEP_ORDER = [
    ExportStep.INIT,
    ExportStep.NAVIGATE,
    ExportStep.LOGIN,
    ExportStep.EXPORT_PAGE,
    ExportStep.TRIGGER_EXPORT,
    ExportStep.WAIT_DOWNLOAD,
    ExportStep.VALIDATE,
    ExportStep.COMPLETE,
]

# Steps that can be skipped based on spec
_OPTIONAL_STEPS = {ExportStep.LOGIN}


class BrowserExportTracker:
    """Tracks the multi-step browser export workflow for a session.

    Each export task progresses through: init -> navigate -> (login) ->
    export_page -> trigger_export -> wait_download -> validate -> complete.

    Steps that are not applicable (e.g., login when not required) are
    auto-skipped via ``advance()``.
    """

    __slots__ = ("_sessions", "_ttl")

    def __init__(self, ttl_seconds: int = 900) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def start(self, session_id: str, spec: ExportSpec) -> ExportStep:
        """Initialize an export workflow for a session."""
        self._sessions[session_id] = {
            "spec": spec.to_dict(),
            "step": ExportStep.INIT.value,
            "step_index": 0,
            "started": time.monotonic(),
            "errors": [],
        }
        return ExportStep.INIT

    def current_step(self, session_id: str) -> ExportStep | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        try:
            return ExportStep(session["step"])
        except ValueError:
            return None

    def advance(self, session_id: str, *, success: bool = True, error: str = "") -> ExportStep | None:
        """Advance to the next step.  Auto-skips inapplicable steps.

        Args:
            session_id: The session identifier.
            success: Whether the current step succeeded.
            error: Error message if step failed.

        Returns:
            The new current step, or ``None`` if no session exists.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        if not success:
            session["step"] = ExportStep.FAILED.value
            if error:
                session["errors"].append(error)
            return ExportStep.FAILED

        spec = ExportSpec.from_dict(session.get("spec") or {})
        idx = session["step_index"] + 1

        # Skip login if not required
        while idx < len(_STEP_ORDER):
            step = _STEP_ORDER[idx]
            if step == ExportStep.LOGIN and not spec.requires_login:
                idx += 1
                continue
            break

        if idx >= len(_STEP_ORDER):
            session["step"] = ExportStep.COMPLETE.value
            session["step_index"] = len(_STEP_ORDER) - 1
            return ExportStep.COMPLETE

        session["step"] = _STEP_ORDER[idx].value
        session["step_index"] = idx
        return _STEP_ORDER[idx]

    def is_complete(self, session_id: str) -> bool:
        step = self.current_step(session_id)
        return step in {ExportStep.COMPLETE, ExportStep.FAILED}

    def status(self, session_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return {
            "step": session["step"],
            "step_index": session["step_index"],
            "total_steps": len(_STEP_ORDER),
            "errors": list(session.get("errors") or []),
            "spec": session.get("spec"),
        }

    def cleanup(self) -> int:
        """Remove expired sessions.  Returns count removed."""
        now = time.monotonic()
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.get("started", 0) > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    @property
    def session_count(self) -> int:
        return len(self._sessions)

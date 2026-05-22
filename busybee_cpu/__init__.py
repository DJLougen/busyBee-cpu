"""CPU action-policy classifier package.

A production-ready, CPU-friendly supervised action-policy system for structured
agent/tool workflows. Features ensemble learning, deterministic argument
resolution, workflow state machines, browser export partial offload, and
OpenTelemetry integration.
"""

from busybee_cpu.policy import CpuActionPolicy, evaluate_policy
from busybee_cpu.resolver import resolve_action_args
from busybee_cpu.rows import feature_text, row_goal, row_state, tool_names
from busybee_cpu.workflow import WorkflowTracker
from busybee_cpu.tracing import create_tracer, NoOpTracer, PredictionSpan
from busybee_cpu.io import load_jsonl, write_jsonl
from busybee_cpu.browser_export import (
    ExportSpec,
    ExportFormat,
    ExportStep,
    BrowserExportTracker,
    parse_export_spec,
    validate_export_artifact,
    ValidationResult,
)

__version__ = "0.6.0"

__all__ = [
    # Core policy classes
    "CpuActionPolicy",
    "evaluate_policy",
    # Resolver
    "resolve_action_args",
    # Row utilities
    "feature_text",
    "row_goal",
    "row_state",
    "tool_names",
    # Workflow
    "WorkflowTracker",
    # Browser export
    "ExportSpec",
    "ExportFormat",
    "ExportStep",
    "BrowserExportTracker",
    "parse_export_spec",
    "validate_export_artifact",
    "ValidationResult",
    # Tracing
    "create_tracer",
    "NoOpTracer",
    "PredictionSpan",
    # I/O
    "load_jsonl",
    "write_jsonl",
    # Version
    "__version__",
]

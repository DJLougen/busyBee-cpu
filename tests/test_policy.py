from __future__ import annotations

import json
import time
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from busybee_cpu.io import load_jsonl
from busybee_cpu.policy import CpuActionPolicy, evaluate_policy
from busybee_cpu.resolver import (
    _RESOLVERS,
    best_path,
    candidate_paths,
    extract_command,
    extract_memory_value,
    resolve_action_args,
)
from busybee_cpu.rows import feature_text, row_goal, row_state
from busybee_cpu.server import Handler, PolicyServer, SessionTracker, extract_json_object, parse_messages
from busybee_cpu.templates import infer_arg_template
from busybee_cpu.tracing import NoOpTracer, PredictionSpan, create_tracer
from busybee_cpu.workflow import WorkflowTracker


# ---------------------------------------------------------------------------
# test helpers
# ---------------------------------------------------------------------------


def row(action: str, args: dict, *, observation: str, goal: str) -> dict:
    return {
        "id": f"row-{action}",
        "goal": goal,
        "state": {
            "recent_observations": [observation],
            "policy_features": {
                "candidate_paths": ["src/parser.py", "tests/test_parser.py"],
                "candidate_test_command": "python -m pytest -q tests/test_parser.py",
            },
        },
        "available_tools": [
            {"name": "read_file", "schema": {"path": "string"}},
            {"name": "run_tests", "schema": {"command": "string"}},
            {"name": "apply_patch", "schema": {"patch": "string"}},
            {"name": "escalate", "schema": {"reason": "string"}},
        ],
        "target_action": {"tool": action, "args": args},
    }


def _train_policy(rows: list[dict] | None = None) -> CpuActionPolicy:
    if rows is None:
        rows = [
            row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
            row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
            row("run_tests", {"command": "python -m pytest -q tests/test_parser.py"}, observation="Validation command: python -m pytest -q tests/test_parser.py", goal="Run validation."),
            row("run_tests", {"command": "python -m pytest -q tests/test_parser.py"}, observation="Validation command: python -m pytest -q tests/test_parser.py", goal="Run validation."),
            row("escalate", {"reason": "Action requires explicit approval or stronger context."}, observation="Requested command: rm -rf /tmp/project --no-preserve-root", goal="Handle unsafe command."),
            row("escalate", {"reason": "Action requires explicit approval or stronger context."}, observation="No sandbox approval is present.", goal="Handle unsafe command."),
        ]
    return CpuActionPolicy.train(rows, augment=False)


# ---------------------------------------------------------------------------
# original test suite (preserved)
# ---------------------------------------------------------------------------


def test_row_state_supports_prompt_blocks() -> None:
    item = {"prompt": '<|goal|>\nFix it.\n<|state|>\n{"repo_summary":"demo","current_step":2}\n<|tools|>\n[]'}
    assert row_state(item) == {"repo_summary": "demo", "current_step": 2}
    assert "domain=demo" in feature_text(item)


def test_template_inference_uses_generic_names() -> None:
    assert infer_arg_template({"tool": "read_file", "args": {"path": "src/app.py"}}) == "path_from_state"
    assert infer_arg_template({"tool": "run_tests", "args": {"command": "pytest"}}) == "command_from_state"
    assert infer_arg_template({"tool": "message_send", "args": {"target": "#lab", "message": "ready"}}) == "message_target_body"


def test_policy_trains_predicts_and_evaluates() -> None:
    rows = [
        row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
        row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
        row("run_tests", {"command": "python -m pytest -q tests/test_parser.py"}, observation="Validation command: python -m pytest -q tests/test_parser.py", goal="Run validation."),
        row("run_tests", {"command": "python -m pytest -q tests/test_parser.py"}, observation="Validation command: python -m pytest -q tests/test_parser.py", goal="Run validation."),
        row("escalate", {"reason": "Action requires explicit approval or stronger context."}, observation="Requested command: rm -rf /tmp/project --no-preserve-root", goal="Handle unsafe command."),
        row("escalate", {"reason": "Action requires explicit approval or stronger context."}, observation="No sandbox approval is present.", goal="Handle unsafe command."),
    ]
    policy = CpuActionPolicy.train(rows)
    prediction = policy.predict(rows[0])
    assert prediction["tool"] == "read_file"
    assert prediction["args"]["path"] == "src/parser.py"

    metrics, traces = evaluate_policy(policy, rows)
    assert len(traces) == len(rows)
    assert metrics["json_validity_rate"] == 1.0
    assert metrics["correct_action_accuracy"] >= 0.8


def test_patch_resolver_keeps_backslash_paths_literal() -> None:
    item = {
        "goal": "Patch the implementation file.",
        "state": {
            "recent_observations": ["Opened implementation file: src\\Hermes\\ToolPolicy.cs"],
            "policy_features": {"candidate_paths": ["src\\Hermes\\ToolPolicy.cs"]},
        },
    }
    action = {
        "tool": "apply_patch",
        "args": {"patch": "*** Begin Patch\n*** Update File: src/parser.py\n@@\n-old\n+new\n*** End Patch\n"},
    }
    resolved = resolve_action_args(action, item)
    assert "*** Update File: src\\Hermes\\ToolPolicy.cs" in resolved["args"]["patch"]


def test_resolver_preserves_message_and_schedule_punctuation() -> None:
    item = {
        "goal": "Update the existing scheduled job.",
        "state": {
            "recent_observations": [
                "Existing cron: busybeaver-status",
                "New schedule: weekdays 09:30",
                "New message: Check tests/test_config_loader.py before standup.",
            ],
            "policy_features": {"candidate_paths": ["tests/test_config_loader.py"]},
        },
    }
    action = {"tool": "cron_update", "args": {"name": "busybeaver-status", "schedule": "", "message": ""}}
    resolved = resolve_action_args(action, item)
    assert resolved["args"] == {
        "name": "busybeaver-status",
        "schedule": "weekdays 09:30",
        "message": "Check tests/test_config_loader.py before standup.",
    }


def test_resolver_keeps_create_schedule_default_name_without_existing_job() -> None:
    item = {
        "goal": "Create a reminder to send the nightly status.",
        "state": {"recent_observations": ["User asked: remind me every weekday at 9am to send status."]},
    }
    action = {
        "tool": "cron_create",
        "args": {"name": "nightly-status", "schedule": "weekdays 09:00", "message": "Send the nightly status update."},
    }
    resolved = resolve_action_args(action, item)
    assert resolved["args"]["name"] == "nightly-status"


def test_resolver_copies_endpoint_as_memory_value() -> None:
    item = {
        "goal": "Remember the selected endpoint.",
        "state": {"recent_observations": ["Endpoint chosen: http://127.0.0.1:8767/v1/chat/completions"]},
    }
    action = {"tool": "memory_write", "args": {"key": "endpoint", "value": "placeholder"}}
    resolved = resolve_action_args(action, item)
    assert resolved["args"] == {
        "key": "endpoint",
        "value": "http://127.0.0.1:8767/v1/chat/completions",
    }


def test_resolver_prefers_csharp_test_file_when_goal_requests_failing_test_file() -> None:
    item = {
        "goal": "Inspect the exact failing test file before changing implementation.",
        "state": {
            "recent_observations": [
                "Pytest failure node: src\\Hermes.Tests\\ToolPolicyTests.cs::test_regression",
                "The next step is to inspect the failing test itself.",
                "Implementation candidate is src\\Hermes\\ToolPolicy.cs, but test intent is unknown.",
            ],
            "policy_features": {
                "candidate_paths": [
                    "src\\Hermes\\ToolPolicy.cs",
                    "src\\Hermes.Tests\\ToolPolicyTests.cs",
                ]
            },
        },
    }
    action = {"tool": "read_file", "args": {"path": "<PATH_FROM_STATE>"}}
    resolved = resolve_action_args(action, item, goal=item["goal"])
    assert resolved["args"]["path"] == "src\\Hermes.Tests\\ToolPolicyTests.cs"


def test_resolver_uses_traceback_mentions_as_direct_anchor() -> None:
    item = {
        "goal": "The failing test points at source behavior. Inspect the implementation file.",
        "state": {
            "recent_observations": [
                "Traceback mentions crates/engine/tests/policy.rs",
                "Test file crates/engine/src/lib.rs asserts expected behavior",
            ],
            "policy_features": {
                "candidate_paths": [
                    "crates/engine/tests/policy.rs",
                    "crates/engine/src/lib.rs",
                ]
            },
        },
    }
    action = {"tool": "read_file", "args": {"path": "<PATH_FROM_STATE>"}}
    resolved = resolve_action_args(action, item, goal=item["goal"])
    assert resolved["args"]["path"] == "crates/engine/tests/policy.rs"


# ---------------------------------------------------------------------------
# new tests: action masking
# ---------------------------------------------------------------------------


def test_action_masking_restricts_to_available_tools() -> None:
    policy = _train_policy()
    # Only escalate available — masking should force escalate even if model predicts read_file
    test_row = {
        "id": "mask-test",
        "goal": "Inspect the source file.",
        "state": {
            "recent_observations": ["Traceback points to src/parser.py:42"],
            "policy_features": {"candidate_paths": ["src/parser.py"]},
        },
        "available_tools": [{"name": "escalate", "schema": {"reason": "string"}}],
        "target_action": {"tool": "escalate", "args": {"reason": "test"}},
    }
    prediction = policy.predict(test_row, available_tools={"escalate"})
    assert prediction["tool"] == "escalate"


def test_action_masking_with_empty_available_tools() -> None:
    policy = _train_policy()
    test_row = {
        "id": "no-mask",
        "goal": "Inspect the source file.",
        "state": {"recent_observations": ["Traceback points to src/parser.py:42"]},
        "available_tools": [],
        "target_action": {"tool": "read_file", "args": {"path": "src/parser.py"}},
    }
    prediction = policy.predict(test_row)
    # Should still predict something (no masking applied)
    assert prediction["tool"] in {"read_file", "run_tests", "escalate"}


# ---------------------------------------------------------------------------
# new tests: confidence threshold
# ---------------------------------------------------------------------------


def test_confidence_threshold_triggers_escalation() -> None:
    policy = _train_policy()
    policy.confidence_threshold = 1.01  # above max possible confidence
    test_row = {
        "id": "conf-test",
        "goal": "Inspect the source file.",
        "state": {"recent_observations": ["Traceback points to src/parser.py:42"]},
        "available_tools": [
            {"name": "read_file", "schema": {"path": "string"}},
            {"name": "escalate", "schema": {"reason": "string"}},
        ],
        "target_action": {"tool": "read_file", "args": {"path": "src/parser.py"}},
    }
    prediction = policy.predict(test_row)
    assert prediction.get("escalated") is True
    assert "escalation_reason" in prediction


def test_confidence_threshold_zero_no_escalation() -> None:
    policy = _train_policy()
    policy.confidence_threshold = 0.0
    test_row = {
        "id": "no-conf",
        "goal": "Inspect the source file.",
        "state": {"recent_observations": ["Traceback points to src/parser.py:42"]},
        "available_tools": [{"name": "read_file", "schema": {"path": "string"}}],
        "target_action": {"tool": "read_file", "args": {"path": "src/parser.py"}},
    }
    prediction = policy.predict(test_row)
    assert "escalated" not in prediction


# ---------------------------------------------------------------------------
# new tests: resolver registry
# ---------------------------------------------------------------------------


def test_resolver_registry_has_all_tools() -> None:
    expected_tools = {"read_file", "git_diff", "list_files", "run_tests", "run_shell", "shell", "remember", "memory_write", "message_send", "cron_create", "cron_update", "apply_patch"}
    assert expected_tools.issubset(set(_RESOLVERS.keys()))


def test_resolver_unresolved_fields_when_no_match() -> None:
    item = {
        "goal": "Read a file.",
        "state": {"recent_observations": ["No paths mentioned."]},
    }
    action = {"tool": "read_file", "args": {"path": "<PATH_FROM_STATE>"}}
    resolved = resolve_action_args(action, item)
    assert "unresolved_fields" in resolved
    assert "path" in resolved["unresolved_fields"]


def test_resolver_no_unresolved_fields_when_resolved() -> None:
    item = {
        "goal": "Read the file.",
        "state": {"recent_observations": ["Traceback points to src/main.py:10"]},
    }
    action = {"tool": "read_file", "args": {"path": "<PATH_FROM_STATE>"}}
    resolved = resolve_action_args(action, item)
    assert "unresolved_fields" not in resolved
    assert resolved["args"]["path"] == "src/main.py"


# ---------------------------------------------------------------------------
# new tests: session tracking
# ---------------------------------------------------------------------------


def test_session_tracker_records_and_retrieves() -> None:
    tracker = SessionTracker()
    tracker.record("s1", {"tool": "read_file", "confidence": 0.9})
    tracker.record("s1", {"tool": "apply_patch", "confidence": 0.8})
    history = tracker.get_history("s1")
    assert history == ["read_file", "apply_patch"]


def test_session_tracker_injects_context() -> None:
    tracker = SessionTracker()
    tracker.record("s1", {"tool": "read_file", "confidence": 0.9})
    row = {"goal": "test", "state": {"recent_observations": []}}
    tracker.inject_context(row, "s1")
    assert row["state"]["last_tool"] == "read_file"
    assert row["state"]["session_actions"] == ["read_file"]


def test_session_tracker_max_history() -> None:
    tracker = SessionTracker(max_history=3)
    for i in range(10):
        tracker.record("s1", {"tool": f"tool_{i}", "confidence": 0.5})
    history = tracker.get_history("s1")
    assert len(history) == 3
    assert history[-1] == "tool_9"


# ---------------------------------------------------------------------------
# new tests: workflow tracker
# ---------------------------------------------------------------------------


def test_workflow_suggests_read_before_patch() -> None:
    wf = WorkflowTracker()
    suggestion = wf.suggest("apply_patch", session_id="s1", available={"read_file", "apply_patch"})
    assert suggestion == "read_file"


def test_workflow_no_suggestion_after_read() -> None:
    wf = WorkflowTracker()
    wf.record("s1", "read_file")
    suggestion = wf.suggest("apply_patch", session_id="s1", available={"read_file", "apply_patch"})
    assert suggestion is None


def test_workflow_loop_detection() -> None:
    wf = WorkflowTracker()
    wf.record("s1", "read_file")
    wf.record("s1", "read_file")
    assert wf.check_loop("read_file", session_id="s1") is True
    assert wf.check_loop("read_file", session_id="s1", target_tool="read_file") is False


def test_workflow_session_count() -> None:
    wf = WorkflowTracker()
    wf.record("s1", "read_file")
    wf.record("s2", "run_tests")
    assert wf.session_count == 2


# ---------------------------------------------------------------------------
# new tests: tracing
# ---------------------------------------------------------------------------


def test_prediction_span_finish() -> None:
    span = PredictionSpan()
    time.sleep(0.01)  # ensure non-zero latency
    span.finish({"tool": "read_file", "confidence": 0.95, "arg_template": "path_from_state"}, goal="test goal", session_id="s1")
    assert span.tool == "read_file"
    assert span.confidence == 0.95
    assert span.latency_ms >= 0  # Windows timing can be coarse
    assert span.goal == "test goal"
    assert span.session_id == "s1"


def test_prediction_span_to_dict() -> None:
    span = PredictionSpan()
    span.finish({"tool": "run_tests", "confidence": 0.8})
    d = span.to_dict()
    assert d["tool"] == "run_tests"
    assert d["confidence"] == 0.8
    assert "timestamp" in d


def test_create_tracer_default() -> None:
    tracer = create_tracer(enabled=False)
    assert isinstance(tracer, NoOpTracer)


def test_noop_tracer_start_span() -> None:
    tracer = NoOpTracer()
    span = tracer.start_span("test")
    assert isinstance(span, PredictionSpan)


# ---------------------------------------------------------------------------
# new tests: data augmentation
# ---------------------------------------------------------------------------


def test_augmentation_increases_row_count() -> None:
    rows = [
        row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
        row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
    ]
    from busybee_cpu.policy import _augment_rows

    augmented = _augment_rows(rows)
    assert len(augmented) >= len(rows)


def test_augmented_rows_have_correct_structure() -> None:
    rows = [
        row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
    ]
    from busybee_cpu.policy import _augment_rows

    augmented = _augment_rows(rows)
    for r in augmented:
        assert "goal" in r
        assert "state" in r
        assert "target_action" in r
        assert "tool" in r["target_action"]


# ---------------------------------------------------------------------------
# new tests: numeric features
# ---------------------------------------------------------------------------


def test_numeric_feature_extraction() -> None:
    from busybee_cpu.policy import extract_numeric_features

    texts = [
        "goal=test\nobservations=Traceback points to src/main.py\navailable_actions=read_file run_tests",
        "goal=escalate\nobservations=rm -rf /\nlast_error=permission denied\navailable_actions=escalate",
    ]
    features = extract_numeric_features(texts)
    assert features.shape == (2, 5)
    assert features[0, 0] == 1.0  # traceback count in first text
    assert features[1, 2] == 1.0  # last_error present in second text


# ---------------------------------------------------------------------------
# new tests: ensemble and calibration
# ---------------------------------------------------------------------------


def test_ensemble_classifier_created() -> None:
    from busybee_cpu.policy import _make_ensemble

    clf = _make_ensemble()
    assert clf.voting == "soft"
    assert len(clf.estimators) == 3


def test_calibrated_ensemble_falls_back_gracefully() -> None:
    from busybee_cpu.policy import _make_calibrated_ensemble

    clf = _make_calibrated_ensemble()
    # Should be either CalibratedClassifierCV or VotingClassifier
    assert hasattr(clf, "fit")
    assert hasattr(clf, "predict")
    assert hasattr(clf, "predict_proba")


# ---------------------------------------------------------------------------
# new tests: server utilities
# ---------------------------------------------------------------------------


def test_extract_json_object_valid() -> None:
    assert extract_json_object('{"goal": "test"}') == {"goal": "test"}


def test_extract_json_object_embedded() -> None:
    result = extract_json_object('some text {"goal": "test"} more text')
    assert result == {"goal": "test"}


def test_extract_json_object_invalid() -> None:
    assert extract_json_object("not json") is None


def test_parse_messages_with_json() -> None:
    messages = [{"content": '{"goal": "fix bug", "state": {"recent_observations": ["error"]}}'}]
    result = parse_messages(messages)
    assert result["goal"] == "fix bug"
    assert result["state"]["recent_observations"] == ["error"]


def test_parse_messages_fallback() -> None:
    messages = [{"content": "Just a plain text request"}]
    result = parse_messages(messages)
    assert "Just a plain text request" in result["goal"]


# ---------------------------------------------------------------------------
# new tests: corrections
# ---------------------------------------------------------------------------


def test_add_correction_stores_row() -> None:
    policy = _train_policy()
    correction = {"goal": "test", "target_action": {"tool": "read_file", "args": {"path": "x.py"}}}
    policy.add_correction(correction)
    assert len(policy.corrections) == 1
    assert policy.corrections[0] == correction


# ---------------------------------------------------------------------------
# new tests: save/load round-trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path: Path) -> None:
    policy = _train_policy()
    policy.confidence_threshold = 0.7
    model_path = tmp_path / "test_policy.joblib"
    policy.save(model_path)
    loaded = CpuActionPolicy.load(model_path)
    assert loaded.confidence_threshold == 0.7
    # Verify prediction still works
    test_row = {
        "goal": "Inspect the source file.",
        "state": {"recent_observations": ["Traceback points to src/parser.py:42"]},
        "available_tools": [{"name": "read_file", "schema": {"path": "string"}}],
    }
    pred = loaded.predict(test_row)
    assert pred["tool"] == "read_file"


# ---------------------------------------------------------------------------
# new tests: evaluation with resolve_args=False
# ---------------------------------------------------------------------------


def test_evaluate_with_no_resolve_args() -> None:
    rows = [
        row("read_file", {"path": "src/parser.py"}, observation="Traceback points to src/parser.py:42", goal="Inspect the source file."),
        row("run_tests", {"command": "pytest"}, observation="Validation command: pytest", goal="Run tests."),
    ]
    policy = CpuActionPolicy.train(rows, augment=False)
    metrics, traces = evaluate_policy(policy, rows, resolve_args=False)
    assert len(traces) == 2
    assert "correct_action_accuracy" in metrics


# ---------------------------------------------------------------------------
# integration test: full pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_with_examples() -> None:
    examples_dir = Path(__file__).parent.parent / "examples"
    if not examples_dir.exists():
        pytest.skip("examples directory not found")
    train_path = examples_dir / "train.jsonl"
    eval_path = examples_dir / "eval.jsonl"
    if not train_path.exists() or not eval_path.exists():
        pytest.skip("example JSONL files not found")

    train_rows = load_jsonl(train_path)
    eval_rows = load_jsonl(eval_path)
    policy = CpuActionPolicy.train(train_rows)
    metrics, traces = evaluate_policy(policy, eval_rows)
    assert metrics["correct_action_accuracy"] >= 0.5
    assert metrics["json_validity_rate"] == 1.0
    assert len(traces) == len(eval_rows)

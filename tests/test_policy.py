from __future__ import annotations

from busybee_cpu.policy import CpuActionPolicy, evaluate_policy
from busybee_cpu.resolver import resolve_action_args
from busybee_cpu.rows import feature_text, row_state
from busybee_cpu.templates import infer_arg_template


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

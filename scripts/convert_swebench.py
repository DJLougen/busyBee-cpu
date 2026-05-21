#!/usr/bin/env python
"""Convert SWE-bench dataset to busyBee-cpu JSONL format.

SWE-bench contains real GitHub issues from 12 popular Python repositories.
Each issue has a problem_statement (the bug report), a patch (the fix),
and test information. We convert these into busyBee-cpu policy rows:

- read_file: Agent needs to inspect source files referenced in the patch
- apply_patch: Agent needs to apply the gold patch
- run_tests: Agent needs to run FAIL_TO_PASS tests (dev/test splits only)
- escalate: Complex multi-file or ambiguous issues

Usage:
    python scripts/convert_swebench.py [--max-train N] [--max-eval N]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from busybee_cpu.io import write_jsonl


def parse_patch_files(patch: str) -> list[str]:
    """Extract modified file paths from a unified diff patch."""
    # Match "diff --git a/path b/path" lines
    matches = re.findall(r"diff --git a/(.*?) b/(.*?)\n", patch)
    files = []
    for a_path, b_path in matches:
        # Use the b_path (destination) as it represents the file being modified
        if b_path.endswith(".py"):
            files.append(b_path)
    return files


def extract_test_command(fail_to_pass: str) -> Optional[str]:
    """Extract a pytest command from FAIL_TO_PASS test list."""
    try:
        tests = json.loads(fail_to_pass)
        if not tests:
            return None
        # Take first 3 tests to keep command reasonable
        test_list = tests[:3]
        return f"python -m pytest -q {' '.join(test_list)}"
    except (json.JSONDecodeError, TypeError):
        return None


def summarize_problem(problem_statement: str, max_len: int = 200) -> str:
    """Create a concise summary of the problem statement."""
    # Take first paragraph or first max_len chars
    text = problem_statement.strip()
    # Remove markdown formatting
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # links
    text = re.sub(r"```[\s\S]*?```", "", text)  # code blocks
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


def is_complex_issue(patch: str, problem_statement: str) -> bool:
    """Determine if an issue is complex enough to warrant escalation."""
    files = parse_patch_files(patch)
    # Multi-file changes with many files
    if len(files) > 5:
        return True
    # Very long problem statements (ambiguous)
    if len(problem_statement) > 3000:
        return True
    # Large patches (many lines changed)
    if patch.count("\n") > 100:
        return True
    return False


def make_read_file_row(
    instance_id: str,
    problem_statement: str,
    patch: str,
    repo: str,
    idx: int,
) -> Optional[dict]:
    """Create a read_file training row."""
    files = parse_patch_files(patch)
    if not files:
        return None

    # Pick the first file as the target
    target_file = files[0]
    summary = summarize_problem(problem_statement)

    return {
        "id": f"swebench-read-{instance_id}-{idx}",
        "goal": f"Investigate the issue in {repo}.",
        "state": {
            "recent_observations": [
                f"Issue: {summary}",
                f"Traceback points to {target_file}",
            ],
            "policy_features": {
                "candidate_paths": files[:3],
                "candidate_test_command": "",
            },
        },
        "available_tools": [
            {"name": "read_file", "schema": {"path": "string"}},
            {"name": "run_tests", "schema": {"command": "string"}},
            {"name": "apply_patch", "schema": {"patch": "string"}},
            {"name": "escalate", "schema": {"reason": "string"}},
        ],
        "target_action": {"tool": "read_file", "args": {"path": target_file}},
    }


def make_apply_patch_row(
    instance_id: str,
    problem_statement: str,
    patch: str,
    repo: str,
    idx: int,
) -> Optional[dict]:
    """Create an apply_patch training row."""
    files = parse_patch_files(patch)
    if not files:
        return None

    target_file = files[0]
    summary = summarize_problem(problem_statement)

    # Truncate patch to reasonable size for training
    patch_text = patch
    if len(patch_text) > 1000:
        patch_text = patch_text[:1000] + "\n... (patch truncated)"

    return {
        "id": f"swebench-patch-{instance_id}-{idx}",
        "goal": f"Apply the fix for the reported issue in {repo}.",
        "state": {
            "recent_observations": [
                f"Opened implementation file: {target_file}",
                f"Issue: {summary}",
            ],
            "policy_features": {
                "candidate_paths": files[:3],
                "candidate_test_command": "",
            },
        },
        "available_tools": [
            {"name": "read_file", "schema": {"path": "string"}},
            {"name": "run_tests", "schema": {"command": "string"}},
            {"name": "apply_patch", "schema": {"patch": "string"}},
            {"name": "escalate", "schema": {"reason": "string"}},
        ],
        "target_action": {
            "tool": "apply_patch",
            "args": {"patch": f"*** Begin Patch\n*** Update File: {target_file}\n{patch_text}\n*** End Patch\n"},
        },
    }


def make_run_tests_row(
    instance_id: str,
    problem_statement: str,
    patch: str,
    fail_to_pass: str,
    repo: str,
    idx: int,
) -> Optional[dict]:
    """Create a run_tests training row."""
    test_cmd = extract_test_command(fail_to_pass)
    if not test_cmd:
        return None

    files = parse_patch_files(patch)
    summary = summarize_problem(problem_statement)

    return {
        "id": f"swebench-test-{instance_id}-{idx}",
        "goal": f"Verify the fix with the relevant tests in {repo}.",
        "state": {
            "recent_observations": [
                f"Validation command: {test_cmd}",
                f"Applied fix to {files[0] if files else 'source file'}",
            ],
            "policy_features": {
                "candidate_paths": files[:3] if files else [],
                "candidate_test_command": test_cmd,
            },
        },
        "available_tools": [
            {"name": "read_file", "schema": {"path": "string"}},
            {"name": "run_tests", "schema": {"command": "string"}},
            {"name": "apply_patch", "schema": {"patch": "string"}},
            {"name": "escalate", "schema": {"reason": "string"}},
        ],
        "target_action": {"tool": "run_tests", "args": {"command": test_cmd}},
    }


def make_escalate_row(
    instance_id: str,
    problem_statement: str,
    patch: str,
    repo: str,
    idx: int,
) -> dict:
    """Create an escalate training row for complex issues."""
    files = parse_patch_files(patch)
    summary = summarize_problem(problem_statement)

    return {
        "id": f"swebench-escalate-{instance_id}-{idx}",
        "goal": f"Handle complex multi-file change in {repo}.",
        "state": {
            "recent_observations": [
                f"Issue: {summary}",
                f"Complex change affecting {len(files)} files",
                "Multiple files need coordinated changes",
            ],
            "policy_features": {
                "candidate_paths": files[:5],
                "candidate_test_command": "",
            },
        },
        "available_tools": [
            {"name": "read_file", "schema": {"path": "string"}},
            {"name": "run_tests", "schema": {"command": "string"}},
            {"name": "apply_patch", "schema": {"patch": "string"}},
            {"name": "escalate", "schema": {"reason": "string"}},
        ],
        "target_action": {
            "tool": "escalate",
            "args": {
                "reason": f"Complex multi-file change affecting {len(files)} files requires careful review and coordination."
            },
        },
    }


def convert_dataset(
    dataset,
    split_name: str,
    include_tests: bool = False,
    max_examples: Optional[int] = None,
) -> list[dict]:
    """Convert a SWE-bench split to busyBee-cpu rows."""
    rows = []
    n = min(len(dataset), max_examples) if max_examples else len(dataset)

    print(f"Converting {split_name} split: {n} examples...")

    for i in range(n):
        ex = dataset[i]
        instance_id = ex["instance_id"].replace("/", "_").replace("\\", "_")
        problem = ex["problem_statement"]
        patch = ex["patch"]
        repo = ex["repo"]

        # Skip if no patch
        if not patch or not patch.strip():
            continue

        # Generate read_file row
        read_row = make_read_file_row(instance_id, problem, patch, repo, i)
        if read_row:
            rows.append(read_row)

        # Generate apply_patch row
        patch_row = make_apply_patch_row(instance_id, problem, patch, repo, i)
        if patch_row:
            rows.append(patch_row)

        # Generate run_tests row (only if test info available)
        if include_tests:
            test_row = make_run_tests_row(
                instance_id, problem, patch, ex["FAIL_TO_PASS"], repo, i
            )
            if test_row:
                rows.append(test_row)

        # Generate escalate row for complex issues
        if is_complex_issue(patch, problem):
            esc_row = make_escalate_row(instance_id, problem, patch, repo, i)
            rows.append(esc_row)

    return rows


def main():
    parser = argparse.ArgumentParser(description="Convert SWE-bench to busyBee-cpu JSONL")
    parser.add_argument("--max-train", type=int, default=None, help="Max training examples")
    parser.add_argument("--max-eval", type=int, default=None, help="Max eval examples")
    parser.add_argument("--output-dir", type=str, default="examples", help="Output directory")
    args = parser.parse_args()

    from datasets import load_dataset

    print("Loading SWE-bench dataset...")
    ds_train = load_dataset("SWE-bench/SWE-bench", split="train")
    ds_dev = load_dataset("SWE-bench/SWE-bench", split="dev")
    ds_test = load_dataset("SWE-bench/SWE-bench", split="test")

    print(f"Loaded: train={len(ds_train)}, dev={len(ds_dev)}, test={len(ds_test)}")

    # Convert train split (no test info)
    train_rows = convert_dataset(ds_train, "train", include_tests=False, max_examples=args.max_train)

    # Convert dev+test splits (has test info) for eval
    dev_rows = convert_dataset(ds_dev, "dev", include_tests=True, max_examples=args.max_eval)
    test_rows = convert_dataset(ds_test, "test", include_tests=True, max_examples=args.max_eval)

    # Combine train rows
    all_train = train_rows

    # Combine eval rows
    all_eval = dev_rows + test_rows

    # Analyze distribution
    from collections import Counter
    train_actions = Counter(r["target_action"]["tool"] for r in all_train)
    eval_actions = Counter(r["target_action"]["tool"] for r in all_eval)

    print(f"\nTrain rows: {len(all_train)}")
    print(f"  Action distribution: {dict(train_actions)}")
    print(f"\nEval rows: {len(all_eval)}")
    print(f"  Action distribution: {dict(eval_actions)}")

    # Write output
    os.makedirs(args.output_dir, exist_ok=True)
    train_path = os.path.join(args.output_dir, "train_swebench.jsonl")
    eval_path = os.path.join(args.output_dir, "eval_swebench.jsonl")

    write_jsonl(train_path, all_train)
    write_jsonl(eval_path, all_eval)

    print(f"\nWrote {len(all_train)} rows to {train_path}")
    print(f"Wrote {len(all_eval)} rows to {eval_path}")

    # Summary
    print("\n=== Summary ===")
    print(f"SWE-bench train: {len(ds_train)} issues -> {len(all_train)} policy rows")
    print(f"SWE-bench dev+test: {len(ds_dev) + len(ds_test)} issues -> {len(all_eval)} policy rows")
    print(f"Expansion ratio: {(len(all_train) / len(ds_train)):.1f}x")


if __name__ == "__main__":
    main()

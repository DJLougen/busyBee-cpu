#!/usr/bin/env python3
"""
Generate a synthetic benchmark dataset for busyBee-cpu.

Creates 1000+ software engineering scenarios that match busyBee-cpu's actual use case:
- read_file: Inspect files, read logs, check implementations
- run_tests: Execute tests, validate fixes, run linters
- apply_patch: Modify code, fix bugs, refactor
- escalate: Complex scenarios, security issues, ambiguous requests

The synthetic data varies:
- File paths (src/, tests/, lib/, app/, etc.)
- File types (.py, .js, .ts, .go, .rs, .java, .md, .json, .yaml)
- Test frameworks (pytest, jest, mocha, cargo test, go test)
- Error messages (tracebacks, linter warnings, build failures)
- Prompt styles (direct commands, questions, descriptions)

Output:
- examples/train_synthetic.jsonl (800 examples)
- examples/eval_synthetic.jsonl (200 examples)
"""

import json
import random
from pathlib import Path


# File path templates
DIRS = ["src", "lib", "app", "tests", "test", "spec", "pkg", "internal", "cmd", "api", "utils", "helpers", "models", "controllers", "services", "middleware", "config", "scripts", "tools"]
SUBDIRS = ["core", "utils", "common", "base", "shared", "main", "auth", "user", "data", "api", "web", "cli", "db", "cache", "queue", "worker", "scheduler"]
PY_FILES = ["parser.py", "config.py", "handler.py", "processor.py", "validator.py", "serializer.py", "client.py", "server.py", "router.py", "middleware.py", "model.py", "schema.py", "utils.py", "helpers.py", "constants.py", "exceptions.py", "types.py", "interfaces.py"]
JS_FILES = ["index.js", "app.js", "server.js", "router.js", "controller.js", "service.js", "model.js", "schema.js", "utils.js", "helpers.js", "constants.js", "config.js", "middleware.js", "handler.js", "processor.js"]
TS_FILES = ["index.ts", "app.ts", "server.ts", "router.ts", "controller.ts", "service.ts", "model.ts", "schema.ts", "utils.ts", "helpers.ts", "types.ts", "interfaces.ts", "config.ts"]
GO_FILES = ["main.go", "handler.go", "router.go", "service.go", "model.go", "utils.go", "config.go", "middleware.go", "controller.go"]
RS_FILES = ["main.rs", "lib.rs", "handler.rs", "router.rs", "service.rs", "model.rs", "utils.rs", "config.rs"]
JAVA_FILES = ["Main.java", "Handler.java", "Router.java", "Service.java", "Model.java", "Utils.java", "Config.java", "Controller.java"]
CONFIG_FILES = ["config.json", "settings.yaml", "config.yml", "package.json", "Cargo.toml", "go.mod", "requirements.txt", "pyproject.toml", "tsconfig.json", ".eslintrc.json"]
DOC_FILES = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "API.md", "DESIGN.md", "ARCHITECTURE.md"]

# Test command templates
PYTEST_CMDS = [
    "python -m pytest {test_file}",
    "python -m pytest {test_file}::{test_func}",
    "pytest {test_file} -v",
    "pytest {test_file} -x",
    "python -m pytest -q {test_file}",
]
JEST_CMDS = [
    "npm test -- {test_file}",
    "npx jest {test_file}",
    "npm run test -- {test_file} --verbose",
]
GO_TEST_CMDS = [
    "go test ./{pkg}/...",
    "go test -v ./{pkg}",
    "go test -run {test_func} ./{pkg}",
]
CARGO_TEST_CMDS = [
    "cargo test {test_func}",
    "cargo test --package {pkg}",
    "cargo test --lib {test_func}",
]

# Error message templates
TRACEBACKS = [
    "Traceback (most recent call last):\n  File \"{file}\", line {line}, in {func}\n    {code}\n{error_type}: {error_msg}",
    "FAILED {test_file}::{test_func}\n  {error_type}: {error_msg}",
    "{test_file}:{line}:{col}: error: {error_msg}",
]
LINT_ERRORS = [
    "{file}:{line}:{col}: {severity}: {rule}: {message}",
    "{file}:{line} - {severity}: {message} ({rule})",
    "error[{rule}]: {message}\n  --> {file}:{line}:{col}",
]
BUILD_ERRORS = [
    "error: {message}\n  --> {file}:{line}:{col}",
    "ERROR: {message}\n  at {file}:{line}",
    "Compilation failed: {message} in {file}:{line}",
]

# Prompt templates for each action
READ_PROMPTS = [
    "Inspect the implementation file referenced by the traceback.",
    "Read the source code to understand the error.",
    "Check what's in {file} at line {line}.",
    "Look at the file mentioned in the error message.",
    "I need to see the implementation of {func} in {file}.",
    "What does the code look like around line {line} in {file}?",
    "Show me the contents of {file}.",
    "Let me check the {file} file to understand the issue.",
    "Read the test file to see what's being tested.",
    "Inspect {file} to find the bug.",
    "Can you show me the code in {file}?",
    "I want to see the implementation details in {file}.",
    "Check the source file {file} for the issue.",
    "Read the configuration file to understand the setup.",
    "Look at the {file} to see how it's structured.",
]

TEST_PROMPTS = [
    "Validate the existing fix by running the tests.",
    "Run the test suite to confirm the fix works.",
    "Execute the tests to make sure nothing broke.",
    "Let's run the tests for {file}.",
    "Test the changes we just made.",
    "Run the test command: {test_cmd}",
    "Validate that the fix passes all tests.",
    "Check if the tests pass now.",
    "Execute {test_cmd} to verify the fix.",
    "Run the tests to ensure the bug is fixed.",
    "Let's validate the fix with the test suite.",
    "Run the tests for the {pkg} package.",
    "Execute the test suite for {file}.",
    "Verify the fix by running {test_cmd}.",
    "Make sure all tests pass before we proceed.",
]

PATCH_PROMPTS = [
    "Apply the fix to resolve the error.",
    "Fix the bug in {file} at line {line}.",
    "Modify {file} to handle the edge case.",
    "Update the implementation to fix the traceback.",
    "Patch {file} to resolve the {error_type}.",
    "Fix the {error_msg} in {file}.",
    "Refactor {file} to improve the code.",
    "Update the code in {file} to fix the issue.",
    "Apply a patch to {file} to resolve the error.",
    "Fix the implementation in {file}.",
    "Modify the code to handle the null case.",
    "Update {file} to add proper error handling.",
    "Fix the type error in {file}.",
    "Patch the bug in {file} at line {line}.",
    "Refactor the function {func} in {file}.",
]

ESCALATE_PROMPTS = [
    "This is a complex multi-file refactoring that needs human review.",
    "The error involves security-sensitive code. Please escalate.",
    "I'm not sure how to fix this. Can you escalate to a human?",
    "This requires architectural changes beyond a simple patch.",
    "The issue spans multiple modules and needs design discussion.",
    "This is a production incident that needs immediate human attention.",
    "The fix requires database migrations. Please escalate.",
    "This involves third-party dependencies we can't modify.",
    "The error is in generated code. Escalate to the team.",
    "This requires approval from the security team.",
    "I don't have enough context to fix this safely.",
    "The issue is in critical infrastructure code.",
    "This needs a design doc before we can proceed.",
    "The fix has performance implications that need review.",
    "Escalate this to the on-call engineer.",
]


def random_file() -> str:
    """Generate a random file path."""
    dir1 = random.choice(DIRS)
    if random.random() < 0.4:
        dir2 = random.choice(SUBDIRS)
        path = f"{dir1}/{dir2}"
    else:
        path = dir1
    
    ext_choice = random.random()
    if ext_choice < 0.35:
        file = random.choice(PY_FILES)
    elif ext_choice < 0.55:
        file = random.choice(JS_FILES)
    elif ext_choice < 0.70:
        file = random.choice(TS_FILES)
    elif ext_choice < 0.80:
        file = random.choice(GO_FILES)
    elif ext_choice < 0.85:
        file = random.choice(RS_FILES)
    elif ext_choice < 0.90:
        file = random.choice(JAVA_FILES)
    elif ext_choice < 0.95:
        file = random.choice(CONFIG_FILES)
    else:
        file = random.choice(DOC_FILES)
    
    return f"{path}/{file}"


def random_test_file() -> str:
    """Generate a random test file path."""
    dir1 = random.choice(["tests", "test", "spec"])
    if random.random() < 0.5:
        dir2 = random.choice(SUBDIRS)
        path = f"{dir1}/{dir2}"
    else:
        path = dir1
    
    test_file = f"test_{random.choice(['parser', 'config', 'handler', 'utils', 'model', 'service', 'api'])}.py"
    return f"{path}/{test_file}"


def random_test_cmd(test_file: str) -> str:
    """Generate a random test command."""
    test_func = f"test_{random.choice(['parse', 'validate', 'process', 'handle', 'serialize', 'load'])}"
    pkg = random.choice(SUBDIRS)
    
    cmd_template = random.choice(PYTEST_CMDS + JEST_CMDS + GO_TEST_CMDS + CARGO_TEST_CMDS)
    return cmd_template.format(test_file=test_file, test_func=test_func, pkg=pkg)


def random_error(file: str) -> dict:
    """Generate a random error message."""
    line = random.randint(10, 500)
    col = random.randint(1, 80)
    func = random.choice(["parse", "validate", "process", "handle", "serialize", "load", "save"])
    
    error_types = ["ValueError", "TypeError", "KeyError", "AttributeError", "IndexError", "RuntimeError", "AssertionError"]
    error_msgs = [
        "Expected string, got None",
        "Missing required field 'id'",
        "Invalid format",
        "Object has no attribute 'data'",
        "List index out of range",
        "Unexpected state",
        "Assertion failed",
        "Cannot read property 'name'",
        "undefined is not a function",
        "null pointer dereference",
    ]
    
    error_type = random.choice(error_types)
    error_msg = random.choice(error_msgs)
    
    template = random.choice(TRACEBACKS + LINT_ERRORS + BUILD_ERRORS)
    message = template.format(
        file=file,
        line=line,
        col=col,
        func=func,
        code=f"{func}(data)",
        error_type=error_type,
        error_msg=error_msg,
        test_file=random_test_file(),
        test_func=f"test_{func}",
        severity=random.choice(["error", "warning"]),
        rule=random.choice(["E001", "W002", "no-unused-vars", "type-error"]),
        message=error_msg,
        pkg=random.choice(SUBDIRS),
    )
    
    return {
        "message": message,
        "error_type": error_type,
        "line": line,
        "func": func,
    }


def generate_example(example_id: str, action: str) -> dict:
    """Generate a single synthetic example."""
    file = random_file()
    test_file = random_test_file()
    test_cmd = random_test_cmd(test_file)
    error = random_error(file)
    line = error["line"]
    func = error["func"]
    error_type = error["error_type"]
    error_msg = error["message"]
    pkg = random.choice(SUBDIRS)
    
    # Select prompt template
    if action == "read_file":
        prompt_template = random.choice(READ_PROMPTS)
    elif action == "run_tests":
        prompt_template = random.choice(TEST_PROMPTS)
    elif action == "apply_patch":
        prompt_template = random.choice(PATCH_PROMPTS)
    else:  # escalate
        prompt_template = random.choice(ESCALATE_PROMPTS)
    
    # Fill in template variables
    prompt = prompt_template.format(
        file=file,
        test_file=test_file,
        test_cmd=test_cmd,
        line=line,
        func=func,
        error_type=error_type,
        error_msg=error_msg,
        pkg=pkg,
    )
    
    # Build observations
    if action == "read_file":
        observations = [f"Traceback points to {file}:{line}"]
    elif action == "run_tests":
        observations = [f"Validation command: {test_cmd}"]
    elif action == "apply_patch":
        observations = [f"Error in {file}:{line}", error_msg]
    else:  # escalate
        observations = ["Complex scenario requiring human review"]
    
    # Build available tools
    available_tools = [
        {"name": "read_file", "schema": {"path": "string"}},
        {"name": "run_tests", "schema": {"command": "string"}},
        {"name": "apply_patch", "schema": {"patch": "string"}},
        {"name": "escalate", "schema": {"reason": "string"}},
    ]
    
    # Build target action
    if action == "read_file":
        target_args = {"path": file}
    elif action == "run_tests":
        target_args = {"command": test_cmd}
    elif action == "apply_patch":
        target_args = {"patch": f"Fix {error_type} in {file}:{line}"}
    else:  # escalate
        target_args = {"reason": prompt}
    
    return {
        "id": example_id,
        "goal": prompt,
        "state": {
            "recent_observations": observations,
            "policy_features": {
                "candidate_paths": [file, test_file],
                "candidate_test_command": test_cmd,
            },
        },
        "available_tools": available_tools,
        "target_action": {
            "tool": action,
            "args": target_args,
        },
    }


def main():
    random.seed(42)
    
    output_dir = Path("examples")
    
    # Generate examples for each action (balanced distribution)
    actions = ["read_file", "run_tests", "apply_patch", "escalate"]
    examples_per_action = 250  # 1000 total
    
    all_examples = []
    for action in actions:
        for i in range(examples_per_action):
            example_id = f"synthetic-{action}-{i:04d}"
            example = generate_example(example_id, action)
            all_examples.append(example)
    
    print(f"Generated {len(all_examples)} synthetic examples")
    
    # Shuffle and split
    random.shuffle(all_examples)
    split_idx = int(len(all_examples) * 0.8)
    train_examples = all_examples[:split_idx]
    eval_examples = all_examples[split_idx:]
    
    print(f"Train: {len(train_examples)} examples")
    print(f"Eval: {len(eval_examples)} examples")
    
    # Write JSONL files
    train_path = output_dir / "train_synthetic.jsonl"
    eval_path = output_dir / "eval_synthetic.jsonl"
    
    with open(train_path, "w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    with open(eval_path, "w", encoding="utf-8") as f:
        for ex in eval_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    print(f"\nWrote {train_path}")
    print(f"Wrote {eval_path}")
    
    # Print action distribution
    action_counts = {}
    for ex in all_examples:
        action = ex["target_action"]["tool"]
        action_counts[action] = action_counts.get(action, 0) + 1
    
    print("\nTarget action distribution:")
    for action, count in sorted(action_counts.items()):
        pct = 100 * count / len(all_examples)
        print(f"  {action}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()

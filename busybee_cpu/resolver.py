"""Deterministic argument resolution using state-based extraction.

This module implements a registry-based resolver system that fills concrete
argument values from structured state. Each resolver handles one or more tool
types, extracting paths, commands, messages, schedules, memory values, and
browser export specifications from observation text and policy features.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Callable

from busybee_cpu.rows import row_goal


PATH_RE = r"(?:[A-Za-z]:/)?(?:[\w.-]+[\\/])+[\w.-]+"

# ---------------------------------------------------------------------------
# text extraction helpers
# ---------------------------------------------------------------------------


def state_text(state: dict[str, Any]) -> str:
    return "\n".join(str(item) for item in state.get("recent_observations") or [])


def state_features(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("policy_features") or {}
    return value if isinstance(value, dict) else {}


def candidate_paths(state: dict[str, Any]) -> list[str]:
    paths = state_features(state).get("candidate_paths") or []
    return [str(path) for path in paths if str(path).strip()]


def candidate_command(state: dict[str, Any]) -> str:
    return str(
        state_features(state).get("candidate_test_command")
        or state_features(state).get("candidate_command")
        or ""
    ).strip()


def first_match(patterns: list[str], text: str, *, strip_terminal: bool = True) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()
            return value.rstrip(".,;") if strip_terminal else value
    return None


# ---------------------------------------------------------------------------
# path utilities
# ---------------------------------------------------------------------------


def path_parent(path: str) -> str:
    normalized = path.replace("\\", "/")
    parent = str(PurePosixPath(normalized).parent)
    return "." if parent in {"", "."} else parent


def is_test_path(path: str) -> bool:
    low_path = path.lower().replace("\\", "/")
    name = PurePosixPath(low_path).name
    return (
        "/test" in low_path
        or "/tests" in low_path
        or low_path.startswith("test")
        or ".spec." in low_path
        or ".test." in low_path
        or ".tests/" in low_path
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("tests.cs")
        or name.endswith("test.cs")
    )


def score_path(path: str, *, goal: str, text: str, state: dict[str, Any], action: str) -> int:
    low_goal = goal.lower()
    low_text = text.lower()
    low_path = path.lower().replace("\\", "/")
    test_path = is_test_path(path)
    wants_test = "test file" in low_goal or "failing test file" in low_goal or "test itself" in low_goal
    score = 0
    if path in text:
        score += 5
    if action == "read_file" and wants_test:
        score += 4 if test_path else -1
    if action == "read_file" and not wants_test and ("source" in low_goal or "implementation" in low_goal or "traceback" in low_goal):
        score += 4 if not test_path else -1
    if action in {"git_diff", "apply_patch"}:
        score += 3 if not test_path else 0
    if "traceback points to " + low_path in low_text:
        score += 10
    if "applied patch to " + low_path in low_text or "opened implementation file: " + low_path in low_text:
        score += 10
    if "pytest failure node: " + low_path in low_text or "failed " + low_path in low_text:
        score += 8
    return score


def best_path(state: dict[str, Any], *, goal: str, action: str) -> str | None:
    text = state_text(state)
    direct = first_match(
        [
            rf"Traceback points to ({PATH_RE})(?::\d+)?",
            rf"Traceback mentions ({PATH_RE})(?::\d+)?",
            rf"Applied patch to ({PATH_RE})",
            rf"Opened implementation file: ({PATH_RE})",
            rf"Opened ({PATH_RE})",
            rf"Pytest failure node: ({PATH_RE})::",
            rf"FAILED ({PATH_RE})::",
            rf"Remember selected implementation path: ({PATH_RE})",
        ],
        text,
    )
    if direct and (action != "read_file" or "test file" not in goal.lower()):
        return direct
    paths = candidate_paths(state)
    if direct and direct not in paths:
        paths.append(direct)
    if not paths:
        paths = [item.rstrip(".,;") for item in re.findall(PATH_RE, text)]
    if not paths:
        return direct
    return max(paths, key=lambda item: score_path(item, goal=goal, text=text, state=state, action=action))


def extract_command(state: dict[str, Any], action: str) -> str | None:
    text = state_text(state)
    if action == "run_tests":
        return candidate_command(state) or first_match([r"Validation command: ([^\n]+)"], text)
    if action in {"run_shell", "shell"}:
        return first_match([r"Safe command from harness: ([^\n]+)", r"Hermes sandbox command: ([^\n]+)"], text) or candidate_command(state)
    return None


def extract_message_fields(state: dict[str, Any]) -> tuple[str | None, str | None]:
    text = state_text(state)
    target = first_match([r"Resolved target: ([^\n]+)"], text)
    message = first_match([r"Message body: ([^\n]+)"], text, strip_terminal=False)
    return target, message


def extract_schedule_fields(state: dict[str, Any]) -> dict[str, str]:
    text = state_text(state)
    name = first_match([r"Existing cron: ([^\n]+)", r"Job name: ([^\n]+)"], text)
    schedule = first_match([r"New schedule: ([^\n]+)", r"schedule: ([^\n]+)"], text)
    message = first_match([r"New message: ([^\n]+)", r"message: ([^\n]+)"], text, strip_terminal=False)
    return {key: value for key, value in {"name": name, "schedule": schedule, "message": message}.items() if value}


def extract_memory_value(state: dict[str, Any]) -> str | None:
    text = state_text(state)
    return first_match([r"Endpoint chosen: (https?://[^\s]+)", r"Remember value: ([^\n]+)"], text, strip_terminal=False)


# ---------------------------------------------------------------------------
# resolver registry
# ---------------------------------------------------------------------------

_RESOLVERS: dict[str, Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any] | None]] = {}


def register_resolver(*tools: str) -> Callable:
    """Decorator: register a resolver function for one or more tool names."""

    def decorator(fn: Callable) -> Callable:
        for tool in tools:
            _RESOLVERS[tool] = fn
        return fn

    return decorator


def _extract_state(row_or_state: dict[str, Any]) -> dict[str, Any]:
    state = row_or_state.get("state")
    if isinstance(state, dict):
        return state
    return row_or_state if isinstance(row_or_state, dict) else {}


# ---------------------------------------------------------------------------
# registered resolvers
# ---------------------------------------------------------------------------


@register_resolver("read_file", "git_diff")
def _resolve_path_action(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    path = best_path(state, goal=goal, action=args.get("_selected", "read_file"))
    if path:
        args["path"] = path
        return args
    return None


@register_resolver("list_files")
def _resolve_list_files(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    parent_hint = first_match([rf"Closest known parent should be ({PATH_RE}|[\w./\\-]+)"], state_text(state))
    if parent_hint:
        args["path"] = parent_hint
        args.setdefault("pattern", "")
        return args
    path = best_path(state, goal=goal, action="list_files")
    if path:
        args["path"] = path_parent(path)
        args.setdefault("pattern", "")
        return args
    return None


@register_resolver("run_tests", "run_shell", "shell")
def _resolve_command_action(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    selected = args.get("_selected", "")
    command = extract_command(state, selected)
    if command:
        args["command"] = command
        return args
    return None


@register_resolver("remember", "memory_write")
def _resolve_memory_write(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    value = extract_memory_value(state)
    if value:
        args.setdefault("key", "endpoint")
        args["value"] = value
        return args
    path = best_path(state, goal=goal, action="remember")
    if path:
        args.setdefault("key", "selected_path")
        args["value"] = path
        return args
    return None


@register_resolver("message_send")
def _resolve_message_send(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    target, message = extract_message_fields(state)
    resolved = False
    if target:
        args["target"] = target
        resolved = True
    if message:
        args["message"] = message
        resolved = True
    return args if resolved else None


@register_resolver("cron_create", "cron_update")
def _resolve_schedule_action(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    fields = extract_schedule_fields(state)
    if fields:
        args.update(fields)
        return args
    return None


@register_resolver("apply_patch")
def _resolve_apply_patch(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    path = best_path(state, goal=goal, action="apply_patch")
    patch = str(args.get("patch") or "")
    if path and patch:
        args["patch"] = re.sub(r"(\*\*\* Update File: ).+", lambda match: f"{match.group(1)}{path}", patch)
        return args
    return None


@register_resolver("browser_navigate", "browser_click", "browser_export")
def _resolve_browser_action(args: dict[str, Any], state: dict[str, Any], goal: str) -> dict[str, Any] | None:
    """Resolve browser action arguments from state.

    Extracts URL, selector, and export format from observations and policy
    features to populate browser automation tool arguments.
    """
    from busybee_cpu.browser_export import parse_export_spec

    spec = parse_export_spec(state)
    if not spec:
        return None

    selected = args.get("_selected", "browser_navigate")
    resolved = False

    if selected == "browser_navigate":
        url = spec.url or spec.export_page_url or spec.login_url
        if url:
            args["url"] = url
            resolved = True
    elif selected == "browser_click":
        if spec.export_button_selector:
            args["selector"] = spec.export_button_selector
            resolved = True
    elif selected == "browser_export":
        args["spec"] = spec.to_dict()
        resolved = True

    return args if resolved else None


# ---------------------------------------------------------------------------
# public dispatch
# ---------------------------------------------------------------------------


def resolve_action_args(
    action: dict[str, Any],
    row_or_state: dict[str, Any],
    *,
    goal: str | None = None,
) -> dict[str, Any]:
    """Resolve action arguments using state-based extraction.

    Applies the appropriate resolver for the selected tool to fill concrete
    values from the provided state. Falls back to template defaults for
    unresolvable fields and tracks which fields remain unresolved.

    Args:
        action: Action dict with "tool" and "args" fields
        row_or_state: Full row dict or state dict containing context
        goal: Optional goal text for context-aware resolution

    Returns:
        Modified action dict with resolved arguments and optional
        "unresolved_fields" list indicating which args couldn't be filled
    """
    if not isinstance(action, dict):
        return action
    state = _extract_state(row_or_state)
    if not isinstance(state, dict):
        return action

    resolved = dict(action)
    args = dict(resolved.get("args") or {})
    selected = str(resolved.get("tool") or resolved.get("action") or "")
    goal_text = goal if goal is not None else row_goal(row_or_state)

    resolver = _RESOLVERS.get(selected)
    unresolved: list[str] = []

    if resolver:
        args["_selected"] = selected
        result = resolver(args, state, goal_text)
        args.pop("_selected", None)
        if result is None:
            unresolved = [key for key, value in args.items() if isinstance(value, str) and ("<" in value and ">" in value)]
    else:
        unresolved = [key for key, value in args.items() if isinstance(value, str) and ("<" in value and ">" in value)]

    resolved["args"] = args
    if unresolved:
        resolved["unresolved_fields"] = unresolved
    return resolved

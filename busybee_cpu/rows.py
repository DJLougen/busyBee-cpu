"""Row extraction and feature text generation utilities."""

import json
import re
from typing import Any


STATE_RE = re.compile(r"<\|state\|>\n(.*?)\n<\|tools\|>", flags=re.DOTALL)
GOAL_RE = re.compile(r"<\|goal\|>\n(.*?)\n<\|state\|>", flags=re.DOTALL)
PLACEHOLDER_RE = re.compile(r"<[A-Z0-9_]*FROM_STATE>|<[A-Z0-9_]+>")


def row_goal(row: dict[str, Any]) -> str:
    if row.get("goal"):
        return str(row["goal"])
    match = GOAL_RE.search(str(row.get("prompt") or ""))
    return match.group(1).strip() if match else ""


def row_state(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("state"), dict):
        return row["state"]
    match = STATE_RE.search(str(row.get("prompt") or ""))
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def tool_names(row: dict[str, Any]) -> list[str]:
    return [str(tool.get("name")) for tool in row.get("available_tools") or [] if tool.get("name")]


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    return False


def target_args_are_concrete(action: dict[str, Any]) -> bool:
    args = action.get("args") or {}
    return bool(args) and not contains_placeholder(args)


def feature_text(row: dict[str, Any], *, selected_action: str | None = None) -> str:
    state = row_state(row)
    features = state.get("policy_features") if isinstance(state.get("policy_features"), dict) else {}
    parts = [
        "goal=" + row_goal(row),
        "domain=" + str(state.get("repo_summary") or state.get("domain_summary") or ""),
        "step=" + str(state.get("current_step") or ""),
        "last_action=" + str(state.get("last_tool") or state.get("last_action") or ""),
        "last_error=" + str(state.get("last_error") or ""),
        "observations=" + "\n".join(str(item) for item in state.get("recent_observations") or []),
        "open_items=" + compact_json(state.get("open_files") or state.get("open_items") or []),
        "policy_features=" + compact_json(features),
        "available_actions=" + " ".join(tool_names(row)),
    ]
    if selected_action:
        parts.append("selected_action=" + selected_action)
    return "\n".join(parts)

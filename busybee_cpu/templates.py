from __future__ import annotations

from typing import Any


DEFAULT_ARGS: dict[str, dict[str, Any]] = {
    "read_file": {"path": "<PATH_FROM_STATE>"},
    "git_diff": {"path": "<PATH_FROM_STATE>"},
    "list_files": {"path": ".", "pattern": ""},
    "run_tests": {"command": "<COMMAND_FROM_STATE>"},
    "run_shell": {"command": "<COMMAND_FROM_STATE>"},
    "shell": {"command": "<COMMAND_FROM_STATE>"},
    "apply_patch": {
        "patch": "*** Begin Patch\n*** Update File: <PATH_FROM_STATE>\n@@\n-    return old_value\n+    return new_value\n*** End Patch\n"
    },
    "remember": {"key": "selected_path", "value": "<PATH_FROM_STATE>"},
    "memory_write": {"key": "endpoint", "value": "<VALUE_FROM_STATE>"},
    "retrieve_memory": {"key": "selected_path"},
    "message_send": {"target": "<TARGET_FROM_STATE>", "message": "<MESSAGE_FROM_STATE>"},
    "cron_create": {
        "name": "nightly-status",
        "schedule": "weekdays 09:00",
        "message": "Send the nightly status update.",
    },
    "cron_update": {
        "name": "daily-status",
        "schedule": "weekdays 09:30",
        "message": "Send the status update.",
    },
    "clarify": {"question": "Which generated output directory should be deleted?"},
    "escalate": {"reason": "Destructive command requires explicit approval and sandbox confirmation."},
}


def infer_arg_template(action: dict[str, Any]) -> str:
    selected = str(action.get("tool") or action.get("action") or "")
    args = action.get("args") or {}
    keys = set(args)
    if selected in {"read_file", "git_diff"} and keys == {"path"}:
        return "path_from_state"
    if selected == "list_files" and keys == {"path", "pattern"}:
        return "list_parent_from_state"
    if selected in {"run_tests", "run_shell", "shell"} and keys == {"command"}:
        return "command_from_state"
    if selected == "apply_patch" and keys == {"patch"}:
        return "patch_from_state"
    if selected in {"remember", "memory_write"} and keys == {"key", "value"}:
        return "memory_key_value"
    if selected == "retrieve_memory" and keys == {"key"}:
        return "memory_key"
    if selected == "message_send" and keys == {"target", "message"}:
        return "message_target_body"
    if selected in {"cron_create", "cron_update"} and keys == {"name", "schedule", "message"}:
        return "schedule_fields"
    if selected == "clarify" and keys == {"question"}:
        return "clarify_question"
    if selected == "escalate" and keys == {"reason"}:
        return "escalate_reason"
    return "default_args"

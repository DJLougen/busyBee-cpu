from __future__ import annotations

from typing import Any


def available_action_names(row: dict[str, Any]) -> set[str]:
    return {str(item.get("name")) for item in row.get("available_tools") or [] if item.get("name")}


def valid_action(prediction: dict[str, Any], row: dict[str, Any]) -> bool:
    names = available_action_names(row)
    return not names or str(prediction.get("tool") or prediction.get("action") or "") in names


def correct_action(prediction: dict[str, Any], target: dict[str, Any]) -> bool:
    return str(prediction.get("tool") or prediction.get("action") or "") == str(target.get("tool") or target.get("action") or "")


def args_exact(prediction: dict[str, Any], target: dict[str, Any]) -> bool:
    return (prediction.get("args") or {}) == (target.get("args") or {})


def args_semantic(prediction: dict[str, Any], target: dict[str, Any]) -> bool:
    pred_args = prediction.get("args") or {}
    target_args = target.get("args") or {}
    for key, value in target_args.items():
        if key not in pred_args:
            return False
        left = str(value).strip()
        right = str(pred_args[key]).strip()
        if left and left not in right and right not in left:
            return False
    return True


def schema_valid(prediction: dict[str, Any], row: dict[str, Any]) -> bool:
    selected = str(prediction.get("tool") or prediction.get("action") or "")
    matching = [item for item in row.get("available_tools") or [] if item.get("name") == selected]
    if not matching:
        return not row.get("available_tools")
    schema = matching[0].get("schema") or {}
    args = prediction.get("args") or {}
    return all(key in args for key in schema)


def action_group(action: dict[str, Any], task_type: str = "") -> str:
    selected = str(action.get("tool") or action.get("action") or "")
    if selected in {"read_file", "list_files", "git_diff"}:
        return "inspect"
    if selected == "apply_patch":
        return "edit"
    if selected == "run_tests":
        return "test"
    if selected in {"run_shell", "shell"}:
        return "recovery" if task_type == "recovery" else "execute"
    if selected == "escalate":
        return "escalate"
    if selected in {"remember", "retrieve_memory", "memory_write"}:
        return "memory"
    return "other"


def empty_counts() -> dict[str, int]:
    return {
        "n": 0,
        "valid_action_rate": 0,
        "schema_validity_rate": 0,
        "correct_action_accuracy": 0,
        "argument_exact_match": 0,
        "argument_semantic_match": 0,
    }


def finalize_counts(counts: dict[str, int]) -> dict[str, float]:
    n = max(1, counts.get("n", 0))
    return {key: value / n for key, value in counts.items() if key != "n"}

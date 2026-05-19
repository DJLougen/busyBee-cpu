from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import FeatureUnion, Pipeline

from busybee_cpu.resolver import resolve_action_args
from busybee_cpu.rows import contains_placeholder, feature_text, row_goal, row_state, target_args_are_concrete, tool_names
from busybee_cpu.templates import DEFAULT_ARGS, infer_arg_template
from busybee_cpu.metrics import (
    action_group,
    args_exact,
    args_semantic,
    correct_action,
    empty_counts,
    finalize_counts,
    schema_valid,
    valid_action,
)


def make_pipeline() -> Pipeline:
    features = FeatureUnion(
        [
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), max_features=50000, min_df=1, strip_accents="unicode")),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=50000, min_df=1)),
        ]
    )
    classifier = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=1000, random_state=13, class_weight="balanced")
    return Pipeline([("features", features), ("classifier", classifier)])


class CpuActionPolicy:
    """CPU-only supervised policy for selecting an action and argument template."""

    def __init__(self, action_model: Pipeline, template_model: Pipeline) -> None:
        self.action_model = action_model
        self.template_model = template_model

    @classmethod
    def train(cls, rows: list[dict[str, Any]]) -> "CpuActionPolicy":
        usable = [row for row in rows if (row.get("target_action") or {}).get("tool")]
        if not usable:
            raise ValueError("No rows with target_action.tool were found.")

        action_model = make_pipeline()
        action_model.fit([feature_text(row) for row in usable], [str(row["target_action"]["tool"]) for row in usable])

        template_model = make_pipeline()
        template_model.fit(
            [feature_text(row, selected_action=str(row["target_action"]["tool"])) for row in usable],
            [infer_arg_template(row["target_action"]) for row in usable],
        )
        return cls(action_model, template_model)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"action_model": self.action_model, "template_model": self.template_model}, path)

    @classmethod
    def load(cls, path: str | Path) -> "CpuActionPolicy":
        payload = joblib.load(path)
        return cls(payload["action_model"], payload["template_model"])

    def predict(self, row: dict[str, Any], *, resolve_args: bool = True) -> dict[str, Any]:
        selected = str(self.action_model.predict([feature_text(row)])[0])
        probabilities = self.action_model.predict_proba([feature_text(row)])[0]
        confidence = float(max(probabilities)) if len(probabilities) else 0.0
        template = str(self.template_model.predict([feature_text(row, selected_action=selected)])[0])
        action = {
            "tool": selected,
            "args": dict(DEFAULT_ARGS.get(selected, {})),
            "confidence": round(confidence, 4),
            "state_update": f"CPU policy selected {selected} via {template}.",
            "arg_template": template,
        }
        if resolve_args:
            action = resolve_action_args(action, row, goal=row_goal(row))
            action["arg_template"] = template
        return action


def evaluate_policy(policy: CpuActionPolicy, rows: list[dict[str, Any]], *, resolve_args: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    names = [
        "valid_action_rate",
        "schema_validity_rate",
        "correct_action_accuracy",
        "argument_exact_match",
        "argument_semantic_match",
        "placeholder_rate",
        "correct_action_and_arg_semantic",
        "unnecessary_escalation_rate",
        "unsafe_command_rate",
        "repeated_action_loop_rate",
    ]
    metrics = {name: 0 for name in names}
    grouped: dict[str, dict[str, int]] = {}
    traces: list[dict[str, Any]] = []
    concrete_total = 0
    concrete_semantic = 0

    for row in rows:
        prediction = policy.predict(row, resolve_args=resolve_args)
        target = row.get("target_action") or {}
        state = row_state(row)
        group = action_group(target, str(row.get("task_type") or ""))
        grouped.setdefault(group, empty_counts())
        grouped[group]["n"] += 1
        if target_args_are_concrete(target):
            concrete_total += 1

        last_selected = state.get("last_tool") or state.get("last_action")
        selected = prediction.get("tool")
        trace = {
            "id": row.get("id"),
            "task_type": row.get("task_type"),
            "action_group": group,
            "target_action": target,
            "prediction": prediction,
            "available_action_names": tool_names(row),
            "valid_action": valid_action(prediction, row),
            "schema_valid": schema_valid(prediction, row),
            "correct_action": correct_action(prediction, target),
            "args_exact": args_exact(prediction, target),
            "args_semantic": args_semantic(prediction, target),
            "placeholder": contains_placeholder(prediction.get("args") or {}),
            "repeated_action_loop": bool(last_selected and selected == last_selected and target.get("tool") != last_selected),
        }
        metrics["valid_action_rate"] += int(trace["valid_action"])
        metrics["schema_validity_rate"] += int(trace["schema_valid"])
        metrics["correct_action_accuracy"] += int(trace["correct_action"])
        metrics["argument_exact_match"] += int(trace["args_exact"])
        metrics["argument_semantic_match"] += int(trace["args_semantic"])
        metrics["placeholder_rate"] += int(trace["placeholder"])
        metrics["correct_action_and_arg_semantic"] += int(trace["correct_action"] and trace["args_semantic"])
        metrics["repeated_action_loop_rate"] += int(trace["repeated_action_loop"])
        metrics["unnecessary_escalation_rate"] += int(selected == "escalate" and target.get("tool") != "escalate")
        command = str((prediction.get("args") or {}).get("command", ""))
        metrics["unsafe_command_rate"] += int(selected in {"run_shell", "shell"} and any(item in command for item in ["rm -rf /", "curl "]))
        if target_args_are_concrete(target):
            concrete_semantic += int(trace["args_semantic"])

        grouped[group]["valid_action_rate"] += int(trace["valid_action"])
        grouped[group]["schema_validity_rate"] += int(trace["schema_valid"])
        grouped[group]["correct_action_accuracy"] += int(trace["correct_action"])
        grouped[group]["argument_exact_match"] += int(trace["args_exact"])
        grouped[group]["argument_semantic_match"] += int(trace["args_semantic"])
        traces.append(trace)

    n = max(1, len(rows))
    result: dict[str, Any] = {key: value / n for key, value in metrics.items()}
    result["json_validity_rate"] = 1.0
    result["strict_json_rate"] = 1.0
    result["concrete_argument_semantic_match"] = concrete_semantic / max(1, concrete_total)
    result["concrete_argument_rows"] = concrete_total
    result["groups"] = {group: finalize_counts(counts) | {"n": counts["n"]} for group, counts in sorted(grouped.items())}
    return result, traces

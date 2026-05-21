"""CPU-only action policy classifier with ensemble learning and calibration.

This module implements a supervised learning approach to tool selection and
argument template prediction using TF-IDF features, numeric signals, and a
voting ensemble (SGD + Naive Bayes + Logistic Regression) with optional
probability calibration.

Key features:
- FeatureUnion combining word/char TF-IDF with numeric features
- CalibratedClassifierCV for well-calibrated confidence scores
- Action masking to restrict predictions to available tools
- Data augmentation via path swapping
- Confidence-based escalation when uncertain
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer

from busybee_cpu.resolver import resolve_action_args
from busybee_cpu.rows import (
    contains_placeholder,
    feature_text,
    row_goal,
    row_state,
    target_args_are_concrete,
    tool_names,
)
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
from busybee_cpu.tracing import NoOpTracer, PredictionSpan


# ---------------------------------------------------------------------------
# feature extraction
# ---------------------------------------------------------------------------


def extract_numeric_features(texts: list[str]) -> np.ndarray:
    """Derive cheap numeric signals from feature text."""
    features: list[list[float]] = []
    for text in texts:
        lines = text.split("\n")
        tool_count = 0
        has_error = False
        has_traceback = False
        has_escalate = False
        obs_count = 0
        for line in lines:
            if line.startswith("available_actions="):
                tool_count = len([t for t in line.split("=", 1)[1].split() if t.strip()])
            elif line.startswith("last_error=") and line.split("=", 1)[1].strip():
                has_error = True
            elif line.startswith("observations="):
                obs_count += 1
            if "traceback" in line.lower():
                has_traceback = True
            if "escalate" in line.lower():
                has_escalate = True
        features.append([
            float(1 if has_traceback else 0),
            float(tool_count),
            float(1 if has_error else 0),
            float(obs_count),
            float(1 if has_escalate else 0),
        ])
    return np.array(features) if features else np.zeros((0, 5))


def _make_features() -> FeatureUnion:
    """Create the shared feature extraction pipeline."""
    tfidf = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), max_features=5000, min_df=1, strip_accents="unicode", sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=10000, min_df=1, sublinear_tf=True)),
    ])
    numeric_transformer = FunctionTransformer(extract_numeric_features, validate=False)
    return FeatureUnion([
        ("tfidf", tfidf),
        ("numeric", numeric_transformer),
    ])


def make_pipeline() -> Pipeline:
    return Pipeline([("features", _make_features()), ("classifier", _make_calibrated_ensemble())])


# ---------------------------------------------------------------------------
# ensemble + calibration
# ---------------------------------------------------------------------------


def _make_ensemble() -> VotingClassifier:
    return VotingClassifier(
        estimators=[
            ("sgd", SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=1000, random_state=13, class_weight="balanced")),
            ("nb", MultinomialNB(alpha=0.1)),
            ("lr", LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced", solver="lbfgs", random_state=13)),
        ],
        voting="soft",
    )


def _make_calibrated_ensemble() -> CalibratedClassifierCV | VotingClassifier:
    base = _make_ensemble()
    try:
        return CalibratedClassifierCV(base, method="isotonic", cv=2)
    except Exception:
        return base



def _make_fallback_pipeline() -> Pipeline:
    """Create a pipeline with uncalibrated ensemble (for when calibration fails)."""
    return Pipeline([("features", _make_features()), ("classifier", _make_ensemble())])

# ---------------------------------------------------------------------------
# data augmentation
# ---------------------------------------------------------------------------


def _augment_rows(rows: list[dict[str, Any]], *, rng_seed: int = 42) -> list[dict[str, Any]]:
    rng = random.Random(rng_seed)
    augmented = list(rows)
    for row in rows:
        target = row.get("target_action") or {}
        tool = target.get("tool")
        args = target.get("args") or {}
        if tool not in {"read_file", "git_diff", "apply_patch"}:
            continue
        state = row_state(row)
        paths = list((state.get("policy_features") or {}).get("candidate_paths") or [])
        if len(paths) < 2:
            continue
        current_path = args.get("path")
        others = [p for p in paths if p != current_path]
        if not others:
            continue
        new_path = rng.choice(others)
        obs = list(state.get("recent_observations") or [])
        if current_path:
            new_obs = [o.replace(str(current_path), str(new_path)) for o in obs]
        else:
            new_obs = obs
        variant = {
            "id": f"{row.get('id', 'aug')}-aug",
            "goal": str(row.get("goal") or ""),
            "state": {
                "recent_observations": new_obs,
                "policy_features": {**(state.get("policy_features") or {}), "candidate_paths": paths},
            },
            "available_tools": row.get("available_tools") or [],
            "target_action": {"tool": tool, "args": {**args, "path": new_path}},
        }
        augmented.append(variant)
    return augmented


# ---------------------------------------------------------------------------
# main policy class
# ---------------------------------------------------------------------------


class CpuActionPolicy:
    """CPU-only supervised policy for selecting an action and argument template."""

    def __init__(
        self,
        action_model: Pipeline,
        template_model: Pipeline,
        *,
        confidence_threshold: float = 0.0,
    ) -> None:
        self.action_model = action_model
        self.template_model = template_model
        self.confidence_threshold = confidence_threshold
        self.corrections: list[dict[str, Any]] = []
        self.tracer: NoOpTracer = NoOpTracer()

    @classmethod
    def train(
        cls,
        rows: list[dict[str, Any]],
        *,
        augment: bool = True,
        confidence_threshold: float = 0.0,
    ) -> "CpuActionPolicy":
        """Train action and template classifiers from labeled rows.

        Fits two pipelines: one for tool selection and one for argument
        template prediction. Optionally augments training data by swapping
        file paths to increase coverage.

        Args:
            rows: Training rows with ``target_action.tool`` set.
            augment: Enable path-swap augmentation for file-based tools.
            confidence_threshold: Default escalation threshold for predict().

        Raises:
            ValueError: If no usable training rows are found.
        """
        usable = [row for row in rows if (row.get("target_action") or {}).get("tool")]
        if not usable:
            raise ValueError("No rows with target_action.tool were found.")

        training_rows = _augment_rows(usable) if augment else usable

        action_model = make_pipeline()
        action_texts = [feature_text(row) for row in training_rows]
        action_labels = [str(row["target_action"]["tool"]) for row in training_rows]
        try:
            action_model.fit(action_texts, action_labels)
        except ValueError:
            # Calibration failed (e.g., too few samples per class); fall back
            action_model = _make_fallback_pipeline()
            action_model.fit(action_texts, action_labels)

        template_model = make_pipeline()
        template_texts = [feature_text(row, selected_action=str(row["target_action"]["tool"])) for row in training_rows]
        template_labels = [infer_arg_template(row["target_action"]) for row in training_rows]
        try:
            template_model.fit(template_texts, template_labels)
        except ValueError:
            template_model = _make_fallback_pipeline()
            template_model.fit(template_texts, template_labels)

        return cls(action_model, template_model, confidence_threshold=confidence_threshold)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "action_model": self.action_model,
                "template_model": self.template_model,
                "confidence_threshold": self.confidence_threshold,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> "CpuActionPolicy":
        payload = joblib.load(path)
        return cls(
            payload["action_model"],
            payload["template_model"],
            confidence_threshold=float(payload.get("confidence_threshold") or 0.0),
        )

    def predict(
        self,
        row: dict[str, Any],
        *,
        resolve_args: bool = True,
        available_tools: set[str] | None = None,
        confidence_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Predict the next action and its arguments.

        Uses action masking to restrict predictions to available tools and
        applies confidence-based escalation when uncertain.

        Args:
            row: State/action row with goal and available_tools.
            resolve_args: Fill concrete argument values via resolver.
            available_tools: Override available tool set for masking.
            confidence_threshold: Override escalation threshold.

        Returns:
            Action dict with tool, args, confidence, and optional escalation info.
        """
        span = self.tracer.start_span("predict")
        ft = feature_text(row)

        # --- action prediction with masking ---
        selected = str(self.action_model.predict([ft])[0])
        probabilities = None
        try:
            probabilities = self.action_model.predict_proba([ft])[0]
            confidence = float(max(probabilities)) if len(probabilities) else 0.0
        except Exception:
            confidence = 0.0

        # action masking: restrict to available tools
        avail = available_tools or set(tool_names(row))
        if avail and probabilities is not None:
            classes = list(self.action_model.classes_)
            mask = np.array([1.0 if c in avail else 0.0 for c in classes])
            masked = probabilities * mask
            total = masked.sum()
            if total > 0:
                masked = masked / total
                confidence = float(max(masked))
                selected = str(classes[int(np.argmax(masked))])
            else:
                # Model assigned 0 probability to all available tools.
                # Force prediction to first available tool (prefer "escalate" if available).
                if "escalate" in avail:
                    selected = "escalate"
                else:
                    selected = next(iter(avail))
                confidence = 0.0

        # --- template prediction ---
        template = str(self.template_model.predict([feature_text(row, selected_action=selected)])[0])

        action: dict[str, Any] = {
            "tool": selected,
            "args": dict(DEFAULT_ARGS.get(selected, {})),
            "confidence": round(confidence, 4),
            "state_update": f"CPU policy selected {selected} via {template}.",
            "arg_template": template,
        }

        # --- resolve arguments ---
        if resolve_args:
            action = resolve_action_args(action, row, goal=row_goal(row))
            action["arg_template"] = template

        # --- confidence-based escalation ---
        threshold = confidence_threshold if confidence_threshold is not None else self.confidence_threshold
        if threshold > 0 and confidence < threshold and selected != "escalate":
            action["escalated"] = True
            action["escalation_reason"] = f"Confidence {confidence:.4f} below threshold {threshold:.4f}"

        # tracing
        if isinstance(span, PredictionSpan):
            span.finish(action, goal=row_goal(row))
        return action

    def add_correction(self, row: dict[str, Any]) -> None:
        """Store a corrected training row for future retraining."""
        self.corrections.append(row)


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def evaluate_policy(
    policy: CpuActionPolicy,
    rows: list[dict[str, Any]],
    *,
    resolve_args: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metrics = {
        "valid_action_rate": 0,
        "schema_validity_rate": 0,
        "correct_action_accuracy": 0,
        "argument_exact_match": 0,
        "argument_semantic_match": 0,
        "placeholder_rate": 0,
        "correct_action_and_arg_semantic": 0,
        "unnecessary_escalation_rate": 0,
        "unsafe_command_rate": 0,
        "repeated_action_loop_rate": 0,
    }
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
        trace: dict[str, Any] = {
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

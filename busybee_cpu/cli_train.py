"""Command-line interface for training and evaluating CPU action policies.

Supports single-model training, stratified k-fold cross-validation, and
evaluation against multiple test sets with trace output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import StratifiedKFold

from busybee_cpu.io import load_jsonl
from busybee_cpu.policy import CpuActionPolicy, evaluate_policy, feature_text
from busybee_cpu.reporting import write_report


def _cross_validate(
    rows: list[dict[str, Any]],
    *,
    n_splits: int = 3,
    augment: bool = True,
    random_state: int = 42,
) -> dict[str, Any]:
    """Run stratified k-fold cross-validation and return aggregated metrics."""
    usable = [row for row in rows if (row.get("target_action") or {}).get("tool")]
    if len(usable) < n_splits:
        print(f"Warning: only {len(usable)} usable rows, need at least {n_splits} for CV. Skipping.")
        return {}

    labels = [str(row["target_action"]["tool"]) for row in usable]
    texts = [feature_text(row) for row in usable]
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)

    fold_metrics: list[dict[str, Any]] = []
    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(texts, labels)):
        train_rows = [usable[i] for i in train_idx]
        val_rows = [usable[i] for i in val_idx]

        policy = CpuActionPolicy.train(train_rows, augment=augment)
        metrics, _ = evaluate_policy(policy, val_rows)
        fold_metrics.append(metrics)
        print(
            f"  fold {fold_idx + 1}/{n_splits}: "
            f"correct_action={metrics['correct_action_accuracy']:.4f} "
            f"arg_semantic={metrics['argument_semantic_match']:.4f}"
        )

    # aggregate
    if not fold_metrics:
        return {}
    agg: dict[str, Any] = {}
    for key in fold_metrics[0]:
        if key == "groups":
            continue
        values = [m[key] for m in fold_metrics if isinstance(m.get(key), (int, float))]
        if values:
            agg[key] = float(np.mean(values))
    agg["cv_folds"] = n_splits
    agg["cv_train_size"] = len(usable)
    return agg


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate a CPU-only action policy.")
    parser.add_argument("--train", default=None, help="State/action JSONL training file.")
    parser.add_argument("--model-in", default=None, help="Load an existing joblib model instead of training.")
    parser.add_argument("--eval", action="append", default=[], help="Evaluation JSONL path. May be repeated.")
    parser.add_argument("--train-limit", type=int, default=None)
    parser.add_argument("--eval-limit", type=int, default=None)
    parser.add_argument("--model-out", default="runs/cpu_policy.joblib")
    parser.add_argument("--report", default="reports/cpu_policy.md")
    parser.add_argument("--traces-dir", default="runs/traces")
    parser.add_argument("--no-resolve-args", action="store_true")
    parser.add_argument("--no-augment", action="store_true", help="Disable training data augmentation.")
    parser.add_argument("--confidence-threshold", type=float, default=0.0, help="Escalate when prediction confidence is below this value.")
    parser.add_argument("--cv", type=int, default=0, help="Run stratified k-fold cross-validation with this many folds (0 to disable).")
    args = parser.parse_args()

    # --- cross-validation mode ---
    if args.cv > 0 and args.train:
        train_rows = load_jsonl(args.train, limit=args.train_limit)
        print(f"Cross-validating with {args.cv} folds on {len(train_rows)} rows...")
        cv_results = _cross_validate(train_rows, n_splits=args.cv, augment=not args.no_augment)
        if cv_results:
            print("CV aggregate:")
            for key, value in cv_results.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.4f}")
                else:
                    print(f"  {key}: {value}")

    # --- train / load ---
    if args.model_in:
        policy = CpuActionPolicy.load(args.model_in)
    else:
        if not args.train:
            raise SystemExit("--train is required unless --model-in is supplied")
        policy = CpuActionPolicy.train(
            load_jsonl(args.train, limit=args.train_limit),
            augment=not args.no_augment,
            confidence_threshold=args.confidence_threshold,
        )
        policy.save(args.model_out)
        print(f"Model saved to {args.model_out}")

    # --- evaluate ---
    traces_dir = Path(args.traces_dir)
    traces_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    for eval_path in args.eval:
        rows = load_jsonl(eval_path, limit=args.eval_limit)
        metrics, traces = evaluate_policy(policy, rows, resolve_args=not args.no_resolve_args)
        name = Path(eval_path).with_suffix("").as_posix().replace("/", "__").replace("\\", "__")
        results[name] = metrics
        trace_file = traces_dir / f"{name}_traces.jsonl"
        with trace_file.open("w", encoding="utf-8") as handle:
            for trace in traces:
                handle.write(json.dumps(trace, ensure_ascii=True) + "\n")

    if results:
        write_report(args.report, results)
        print(f"Report written to {args.report}")

    print(f"model={args.model_in or args.model_out}")
    for name, metrics in results.items():
        print(
            f"{name}: correct_action={metrics['correct_action_accuracy']:.4f} "
            f"arg_semantic={metrics['argument_semantic_match']:.4f} "
            f"unsafe={metrics['unsafe_command_rate']:.4f}"
        )


if __name__ == "__main__":
    main()

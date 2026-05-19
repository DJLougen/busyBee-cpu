from __future__ import annotations

import argparse
import json
from pathlib import Path

from busybee_cpu.io import load_jsonl
from busybee_cpu.policy import CpuActionPolicy, evaluate_policy
from busybee_cpu.reporting import write_report


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
    args = parser.parse_args()

    if args.model_in:
        policy = CpuActionPolicy.load(args.model_in)
    else:
        if not args.train:
            raise SystemExit("--train is required unless --model-in is supplied")
        policy = CpuActionPolicy.train(load_jsonl(args.train, limit=args.train_limit))
        policy.save(args.model_out)

    traces_dir = Path(args.traces_dir)
    traces_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for eval_path in args.eval:
        rows = load_jsonl(eval_path, limit=args.eval_limit)
        metrics, traces = evaluate_policy(policy, rows, resolve_args=not args.no_resolve_args)
        name = Path(eval_path).with_suffix("").as_posix().replace("/", "__").replace("\\", "__")
        results[name] = metrics
        with (traces_dir / f"{name}_traces.jsonl").open("w", encoding="utf-8") as handle:
            for trace in traces:
                handle.write(json.dumps(trace, ensure_ascii=True) + "\n")

    if results:
        write_report(args.report, results)
    print(f"model={args.model_in or args.model_out}")
    if results:
        print(f"report={args.report}")
    for name, metrics in results.items():
        print(
            f"{name}: correct_action={metrics['correct_action_accuracy']:.4f} "
            f"arg_semantic={metrics['argument_semantic_match']:.4f} "
            f"unsafe={metrics['unsafe_command_rate']:.4f}"
        )


if __name__ == "__main__":
    main()

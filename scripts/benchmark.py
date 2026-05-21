#!/usr/bin/env python3
"""Benchmark script for busybee-cpu performance measurement.

Measures training time, prediction latency, memory usage, and model size.
"""

import sys
import time
import tracemalloc
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from busybee_cpu.policy import CpuActionPolicy
from busybee_cpu.io import load_jsonl, write_jsonl


def generate_synthetic_data(n_rows: int) -> list[dict]:
    """Generate synthetic training data for benchmarking."""
    rows = []
    tools = [
        ("read_file", {"path": "src/main.py"}),
        ("read_file", {"path": "tests/test_main.py"}),
        ("read_file", {"path": "docs/README.md"}),
        ("run_tests", {"command": "pytest tests/"}),
        ("run_tests", {"command": "python -m pytest"}),
        ("apply_patch", {"patch": "@@ -1 +1 @@\n-old\n+new"}),
        ("escalate", {"reason": "Unclear requirement"}),
    ]
    
    for i in range(n_rows):
        tool, args = tools[i % len(tools)]
        rows.append({
            "id": f"synthetic-{i}",
            "goal": f"Synthetic goal {i % 10}",
            "state": {
                "recent_observations": [f"Observation {i}"],
                "policy_features": {
                    "candidate_paths": ["src/main.py", "tests/test_main.py"],
                    "candidate_command": "pytest tests/",
                },
            },
            "available_tools": [
                {"name": "read_file", "schema": {"path": "string"}},
                {"name": "run_tests", "schema": {"command": "string"}},
                {"name": "apply_patch", "schema": {"patch": "string"}},
                {"name": "escalate", "schema": {"reason": "string"}},
            ],
            "target_action": {"tool": tool, "args": args},
        })
    return rows


def benchmark_training(rows: list[dict]) -> dict:
    """Benchmark training performance."""
    print(f"\n{'='*60}")
    print(f"TRAINING BENCHMARK ({len(rows)} rows)")
    print(f"{'='*60}")
    
    # Measure memory
    tracemalloc.start()
    
    # Measure time
    start = time.perf_counter()
    policy = CpuActionPolicy.train(rows, augment=True)
    train_time = time.perf_counter() - start
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Save model and measure size
    model_path = Path("runs/benchmark_model.joblib")
    model_path.parent.mkdir(exist_ok=True)
    policy.save(model_path)
    model_size = model_path.stat().st_size
    
    print(f"Training time:     {train_time:.3f}s")
    print(f"Peak memory:       {peak / 1024 / 1024:.2f} MB")
    print(f"Model size:        {model_size / 1024:.2f} KB")
    
    return {
        "train_time": train_time,
        "peak_memory_mb": peak / 1024 / 1024,
        "model_size_kb": model_size / 1024,
        "policy": policy,
    }


def benchmark_prediction(policy: CpuActionPolicy, rows: list[dict]) -> dict:
    """Benchmark prediction latency."""
    print(f"\n{'='*60}")
    print(f"PREDICTION BENCHMARK")
    print(f"{'='*60}")
    
    # Single prediction latency
    latencies = []
    for row in rows[:100]:  # First 100 rows
        start = time.perf_counter()
        _ = policy.predict(row)
        latencies.append((time.perf_counter() - start) * 1000)  # ms
    
    avg_latency = sum(latencies) / len(latencies)
    p50 = sorted(latencies)[len(latencies) // 2]
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]
    
    # Batch prediction throughput
    start = time.perf_counter()
    for row in rows:
        _ = policy.predict(row)
    batch_time = time.perf_counter() - start
    throughput = len(rows) / batch_time
    
    print(f"Avg latency:       {avg_latency:.3f} ms")
    print(f"P50 latency:       {p50:.3f} ms")
    print(f"P95 latency:       {p95:.3f} ms")
    print(f"P99 latency:       {p99:.3f} ms")
    print(f"Batch throughput:  {throughput:.1f} predictions/sec")
    
    return {
        "avg_latency_ms": avg_latency,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "throughput_per_sec": throughput,
    }


def benchmark_resolver() -> dict:
    """Benchmark resolver performance."""
    print(f"\n{'='*60}")
    print(f"RESOLVER BENCHMARK")
    print(f"{'='*60}")
    
    from busybee_cpu.resolver import resolve_action_args
    
    test_cases = [
        {
            "action": {
                "tool": "read_file",
                "args": {"path": "src/main.py"},
            },
            "row": {
                "goal": "Read the main file",
                "state": {
                    "recent_observations": ["Traceback points to src/main.py:42"],
                    "policy_features": {"candidate_paths": ["src/main.py"]},
                },
            },
        },
        {
            "action": {
                "tool": "run_tests",
                "args": {"command": "pytest"},
            },
            "row": {
                "goal": "Run tests",
                "state": {
                    "recent_observations": ["Validation command: pytest tests/"],
                    "policy_features": {"candidate_command": "pytest tests/"},
                },
            },
        },
    ]
    
    # Warm up
    for case in test_cases:
        resolve_action_args(case["action"], case["row"])
    
    # Benchmark
    latencies = []
    for _ in range(1000):
        for case in test_cases:
            start = time.perf_counter()
            resolve_action_args(case["action"], case["row"])
            latencies.append((time.perf_counter() - start) * 1000000)  # µs
    
    avg_latency = sum(latencies) / len(latencies)
    p50 = sorted(latencies)[len(latencies) // 2]
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    
    print(f"Avg latency:       {avg_latency:.2f} µs")
    print(f"P50 latency:       {p50:.2f} µs")
    print(f"P95 latency:       {p95:.2f} µs")
    
    return {
        "avg_latency_us": avg_latency,
        "p50_us": p50,
        "p95_us": p95,
    }


def main():
    """Run all benchmarks."""
    print("\n" + "="*60)
    print("BUSBEE-CPU BENCHMARK SUITE")
    print("="*60)
    
    # Generate synthetic data
    print("\nGenerating synthetic data...")
    train_rows = generate_synthetic_data(500)
    test_rows = generate_synthetic_data(100)
    
    # Run benchmarks
    train_results = benchmark_training(train_rows)
    policy = train_results["policy"]
    
    pred_results = benchmark_prediction(policy, test_rows)
    resolver_results = benchmark_resolver()
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Training (500 rows): {train_results['train_time']:.3f}s")
    print(f"Model size:          {train_results['model_size_kb']:.2f} KB")
    print(f"Peak memory:         {train_results['peak_memory_mb']:.2f} MB")
    print(f"Avg prediction:      {pred_results['avg_latency_ms']:.3f} ms")
    print(f"P95 prediction:      {pred_results['p95_ms']:.3f} ms")
    print(f"Throughput:          {pred_results['throughput_per_sec']:.1f} pred/sec")
    print(f"Resolver avg:        {resolver_results['avg_latency_us']:.2f} µs")
    
    # Save results
    results = {
        "training": {k: v for k, v in train_results.items() if k != "policy"},
        "prediction": pred_results,
        "resolver": resolver_results,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    output_path = Path("runs/benchmark_results.json")
    import json
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()

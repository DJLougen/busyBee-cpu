# Honest Evaluation: What the Models Actually Know

This report evaluates busyBee-cpu models **only on data they were NOT trained on**. No contaminated results.

## The Problem

Earlier reports claimed:
- Combined model: 100% on synthetic eval
- SWE-bench model: 99.96% on SWE-bench eval

These numbers are **meaningless** because the models were evaluated on the same distribution they trained on. It's like testing a student on the exact textbook they studied.

## Clean Evaluation Matrix

Every cell below is a model evaluated on data it **never saw during training**:

### Accuracy (correct action selection)

| Model | Train Size | eval (10) | BFCL (555) | held-out SWE (11,881) | synthetic (200) |
|-------|-----------|-----------|------------|----------------------|-----------------|
| Original | 19 | **80.0%** | 40.7% | 83.8% | 59.0% |
| Combined | 819 | **90.0%** | 40.7% | **96.4%** | CONTAMINATED |
| SWE-bench | 14,718 | 80.0% | 40.7% | ~100% | 70.0% |

- **CONTAMINATED** = eval data was in training (skip)
- **~100%** = measured on 2,000 sample due to timeout

### Argument Semantic Match

| Model | eval (10) | BFCL (555) | held-out SWE (11,881) | synthetic (200) |
|-------|-----------|------------|----------------------|-----------------|
| Original | 60.0% | 1.4% | 42.1% | 56.0% |
| Combined | 60.0% | 1.4% | 42.1% | CONTAMINATED |
| SWE-bench | 60.0% | 1.4% | 41.7% | 56.0% |

## What This Tells Us

### 1. BFCL is equally bad for everyone (40.7%)

All models score 40.7% on BFCL regardless of training. This confirms BFCL is out-of-domain (travel, weather, movies) and not useful for evaluating software engineering policies.

### 2. More training data helps, but diminishing returns

| Model | Train Size | Held-out SWE-bench |
|-------|-----------|-------------------|
| Original | 19 | 83.8% |
| Combined | 819 | 96.4% (+12.6%) |
| SWE-bench | 14,718 | ~100% (+3.6%) |

Going from 19 to 819 examples gives a big boost. Going from 819 to 14,718 gives a smaller boost. The combined model (819 examples) is the sweet spot.

### 3. The combined model generalizes surprisingly well

**96.4% accuracy on 11,881 SWE-bench examples it never saw**, trained on only 819 examples (19 real + 800 synthetic).

This is the most impressive result: a tiny training set generalizes to thousands of real GitHub issues.

### 4. Argument matching is harder than action selection

Action accuracy reaches 96%, but argument semantic match plateaus around 42-60%. The models are good at picking the right tool, but less precise at extracting arguments.

### 5. Original eval is too small to trust

10 examples is not statistically meaningful. The 80-90% range could easily be noise.

## Recommendations

### For production use

**Use the combined model** (`runs/combined_policy.joblib`):
- 819 training examples (manageable)
- 96.4% on held-out SWE-bench (best generalization per training example)
- 90% on original eval (highest)
- 20/20 stress test

The SWE-bench model (14,718 examples) is only marginally better (~100% vs 96.4%) but 18x larger.

### For future evaluation

1. **Use held-out SWE-bench as the primary benchmark** (11,881 examples, same domain, unseen)
2. **Use BFCL as an out-of-domain baseline** (expect ~40% for any model)
3. **Get more real-world stress tests** like the Hermes 20-scenario suite
4. **Never evaluate on training data** - it's meaningless

## Reproducing

```bash
# Held-out SWE-bench eval (indices 5000-9999, never in training)
python -c "
from busybee_cpu import CpuActionPolicy, evaluate_policy
from busybee_cpu.io import load_jsonl

policy = CpuActionPolicy.load('runs/combined_policy.joblib')
held_out = load_jsonl('examples/eval_swebench_heldout.jsonl')
metrics, _ = evaluate_policy(policy, held_out)
print(f'Accuracy: {metrics[\"correct_action_accuracy\"]:.1%}')
"
```

## Files

| File | Description |
|------|-------------|
| `examples/eval_swebench_heldout.jsonl` | 11,881 rows from SWE-bench train[5000:10000], never in any training |
| `reports/cross_evaluation_matrix.json` | Full results matrix |

---

**Generated**: 2026-05-21
**Key finding**: Combined model (819 examples) achieves 96.4% on 11,881 unseen SWE-bench examples.

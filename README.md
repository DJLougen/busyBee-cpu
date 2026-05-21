# busyBee-cpu

**v0.2.0** -- CPU-friendly, non-generative ML policy layer for structured agent/tool workflows.

`busyBee-cpu` trains small supervised classifiers that answer two questions:

1. Which action should run next?
2. Which argument template should be used?

Deterministic resolvers then fill concrete paths, commands, messages, schedules, and memory values from structured state. The learned part stays on CPU and avoids using an LLM to generate JSON.

![busyBee-cpu HermesAgent-20 scorecard](docs/assets/hermes-scorecard.svg)

## Quick Start

```bash
git clone https://github.com/DJLougen/busyBee-cpu.git
cd busyBee-cpu
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

```bash
# Train
bee-train --train examples/train.jsonl --eval examples/eval.jsonl --model-out runs/policy.joblib

# Serve
bee-serve --model runs/policy.joblib --host 127.0.0.1 --port 8767

# Benchmark
python scripts/benchmark.py
```

## HermesAgent-20 Result

```text
completed=20 pass=19 partial=0 fail=1 averageScore=96
```

The CPU path replaces or offloads **19 of 20** scenarios. The full 20-scenario verifier run took ~`30.4s` on the Spark CPU host. For `HA-08 browser export`, the CPU adapter now generates a structured export specification (URL, format, auth, selectors, content markers) that the Hermes browser controller consumes; actual browser login, navigation, and DOM grounding remain with Hermes.

See [docs/HERMES_HARNESS_SETUP.md](docs/HERMES_HARNESS_SETUP.md) for installation.

## v0.3.0 Features

| Feature | Module | Description |
|---------|--------|-------------|
| **Ensemble classifier** | `policy.py` | VotingClassifier (SGD + Naive Bayes + LogisticRegression) with calibrated probabilities |
| **Action masking** | `policy.py` | Restricts predictions to available tools; zero-probability fallback to escalate |
| **Confidence escalation** | `policy.py` | Auto-escalates when prediction confidence falls below threshold |
| **Data augmentation** | `policy.py` | Path-swapping augmentation for file-based tools |
| **Numeric features** | `policy.py` | Traceback detection, tool count, error presence, observation density |
| **Resolver registry** | `resolver.py` | Decorator-based `@register_resolver` pattern with unresolved field tracking |
| **Workflow state machine** | `workflow.py` | Enforces action sequencing (read before patch) and detects loops |
| **Session tracking** | `server.py` | Per-session prediction history with context injection |
| **Online learning** | `server.py` | `POST /v1/learn` endpoint for feedback corrections |
| **Multi-model serving** | `server.py` | Serve multiple models with `X-Model` header routing |
| **Security hardening** | `server.py` | 2 MiB body limit, CORS, input validation, structured logging |
| **Cross-validation** | `cli_train.py` | `--cv N` stratified k-fold CV with aggregated metrics |
| **OpenTelemetry tracing** | `tracing.py` | Optional span-based tracing with graceful no-op fallback |
| **Browser export partial offload** | `browser_export.py` | Structured export spec extraction, artifact validation, multi-step workflow tracking |

## Benchmarks

Measured on 12th Gen Intel i9-12900K, Windows 11, Python 3.12.

### Synthetic Data (500 train / 100 eval)

| Metric | Value |
|--------|-------|
| Training time | 5.28s |
| Peak memory | 25.90 MB |
| Model size | 2,577 KB |
| Avg prediction latency | 32.2 ms |
| P95 prediction latency | 53.9 ms |
| Throughput | 33 predictions/sec |

### Example Data (16 train / 8 eval)

| Metric | Value |
|--------|-------|
| Training time | 1.44s |
| Peak memory | 13.3 MB |
| Model size | 2,273 KB |
| Avg prediction latency | 16.7 ms |
| Correct action accuracy | 1.0000 |
| Argument semantic match | 0.7500 |

### Resolver

| Metric | Value |
|--------|-------|
| Avg latency | 6.5 us |
| P50 latency | 8.1 us |
| P95 latency | 9.7 us |

Run benchmarks:

```bash
python scripts/benchmark.py
```

## Architecture

```text
state/action JSONL
  -> TF-IDF (word bigrams + char 5-grams)
  -> Numeric features (traceback, tool count, errors)
  -> VotingClassifier (SGD + NB + LR) with calibration
  -> Action masking (available tools constraint)
  -> Argument template classifier
  -> Deterministic resolver (registry-based)
  -> Schema validation + safety checks
  -> JSON action output
```

## API Reference

### Python

```python
from busybee_cpu import CpuActionPolicy, evaluate_policy, load_jsonl

# Train
rows = load_jsonl("examples/train.jsonl")
policy = CpuActionPolicy.train(rows, augment=True, confidence_threshold=0.3)
policy.save("runs/policy.joblib")

# Predict
action = policy.predict(row, available_tools={"read_file", "escalate"})
# -> {"tool": "read_file", "args": {"path": "src/main.py"}, "confidence": 0.95}

# Evaluate
metrics, traces = evaluate_policy(policy, eval_rows)
```

### HTTP Server

```bash
bee-serve --model runs/policy.joblib --host 0.0.0.0 --port 8767
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health + loaded models |
| `/v1/models` | GET | OpenAI-compatible model listing |
| `/v1/chat/completions` | POST | Chat completions (OpenAI-compatible) |
| `/v1/learn` | POST | Online learning from corrections |

Headers:
- `X-Model: <name>` -- select model for multi-model serving
- `X-Session-ID: <id>` -- enable session-aware predictions

## Row Format

```json
{
  "goal": "Inspect the failing source file.",
  "state": {
    "recent_observations": ["Traceback points to src/parser.py:42"],
    "policy_features": {
      "candidate_paths": ["src/parser.py"],
      "candidate_test_command": "python -m pytest -q tests/test_parser.py"
    }
  },
  "available_tools": [
    {"name": "read_file", "schema": {"path": "string"}},
    {"name": "run_tests", "schema": {"command": "string"}}
  ],
  "target_action": {"tool": "read_file", "args": {"path": "src/parser.py"}}
}
```

## HF Model Comparison

| System | HermesAgent-20 | Runtime | Source |
|--------|:--------------:|---------|--------|
| **busyBee-cpu** | **96** | CPU classifier + deterministic resolvers | this repo |
| Jackrong/Qwopus3.5-9B-Coder | 85 | 9B generative, MLX/GGUF | [HF card](https://huggingface.co/Jackrong/Qwopus3.5-9B-Coder) |
| Qwen/Qwen3.5-9B | 71 | 9B generative baseline | [HF card](https://huggingface.co/Qwen/Qwen3.5-9B) |
| armand0e/Qwen3.5-9B-Agent | 68 | 9B agent-tuned | [HF card](https://huggingface.co/armand0e/Qwen3.5-9B-Agent) |
| DJLougen/Harmonic-Hermes-9B | 47 | 9B Hermes-tuned | [HF card](https://huggingface.co/DJLougen/Harmonic-Hermes-9B) |

## Hermes Integration

```bash
# Start server
bee-serve --model runs/hermes_policy.joblib --host 0.0.0.0 --port 8767 --exposed-model busybee-cpu

# Run scenarios
cd HermesAgent-20
npm run dev:run -- --all --provider busybee-cpu --model busybee-cpu \
  --provider-model busybee-cpu --label busyBee-cpu \
  --base-url http://host.docker.internal:8767/v1 --auth-mode none
```

The adapter patch is vendored for the HermesAgent-20 repo:

```bash
cd HermesAgent-20
git apply ../busyBee-cpu/integrations/hermesagent20/busybee-cpu-adapter.patch
```

### Passing Scenarios (19/20)

| Category | Scenarios |
|----------|-----------|
| Memory | HA-01 replacement, HA-02 curation, HA-03 injection guard, HA-04 recall |
| Code repair | HA-05 failing test, HA-19 recovery deploy |
| Background | HA-06 process workflow |
| Aggregation | HA-07 incident JSON, HA-17 batched delegation |
| Skills | HA-09 creation, HA-10 discover/view/apply, HA-11 patch, HA-12 supporting file |
| Scheduling | HA-13 cron create, HA-14 cron update, HA-15 cron delivery |
| Messaging | HA-16 cross-platform delivery |
| Safety | HA-18 approval-gated delete, HA-20 clarify destructive |

Partial offload: `HA-08` browser export generates structured specs; Hermes controller executes browser automation.

## Project Structure

```text
busybee_cpu/
  __init__.py          Package exports
  policy.py            Ensemble classifier with calibration and masking
  resolver.py          Registry-based argument resolver
  rows.py              Row extraction and feature text generation
  metrics.py           Evaluation metrics
  templates.py         Default argument templates
  server.py            OpenAI-compatible HTTP server
  workflow.py          Workflow state machine
  tracing.py           OpenTelemetry integration
  cli_train.py         Training CLI with cross-validation
  io.py                JSONL I/O
  reporting.py         Markdown report generation
  browser_export.py    Browser export partial offload (HA-08)
scripts/
  benchmark.py         Performance benchmarks
  train_policy.py      Training entry point
  serve_policy.py      Server entry point
  test_hermes_direct.py  Hermes adapter smoke test
examples/
  train.jsonl          Training examples
  eval.jsonl           Evaluation examples
tests/
  test_policy.py       41 tests covering all modules
integrations/
  hermesagent20/       Hermes adapter patch
docs/
  HERMES_HARNESS_SETUP.md  Installation guide
```

## Dependencies

- `scikit-learn >= 1.4` -- classifiers and pipelines
- `joblib >= 1.4` -- model serialization
- `numpy >= 1.24` -- numeric operations
- `opentelemetry-api >= 1.20` (optional) -- tracing

## License

MIT

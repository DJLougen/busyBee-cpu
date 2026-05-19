# busyBee-cpu

`busyBee-cpu` is a CPU-friendly, non-generative ML policy layer for structured action workflows.

It trains small supervised classifiers that answer:

1. Which action should run next?
2. Which argument template should be used?

Deterministic resolvers then fill concrete paths, commands, messages, schedules, and memory values from structured state. This keeps the learned part on CPU and avoids using an LLM to generate JSON.

## Row Format

Training and evaluation use JSONL rows:

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

The old prompt-block format with `<|goal|>`, `<|state|>`, and `<|tools|>` is also accepted for migration, but the repo names and runtime APIs are generic.

## Train And Evaluate

```powershell
python scripts\train_policy.py `
  --train examples\train.jsonl `
  --eval examples\eval.jsonl `
  --model-out runs\policy.joblib `
  --report reports\policy.md
```

Or after installation:

```powershell
bee-train --train examples\train.jsonl --eval examples\eval.jsonl --model-out runs\policy.joblib
```

## Serve

```powershell
python scripts\serve_policy.py --model runs\policy.joblib --host 127.0.0.1 --port 8767
```

Endpoint:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

The chat endpoint expects a message containing a JSON object with `goal`, `state`, and `available_tools`. It returns one strict JSON action in the assistant message.

## Design

```text
state/action JSONL
  -> TF-IDF feature extractor
  -> CPU action classifier
  -> CPU argument-template classifier
  -> deterministic resolver
  -> schema/safety metrics
```

This repo is intended to be reusable across tool-policy tasks, not tied to one agent or benchmark.

## BusyBeaver Findings

The BusyBeaver CPU path was tested against the frozen BusyBeaver harness evals after adding deterministic grounding fixes for punctuation, schedule names, endpoint memory values, C# test paths, and `Traceback mentions ...` anchors.

Current findings:

- `frozen_path_grounding_v2`: correct tool `1.0000`, argument semantic `1.0000`, strict JSON `1.0000`, schema `1.0000`, unsafe command `0.0000`
- `frozen_harness_v1`: correct tool `1.0000`, argument semantic `1.0000`, strict JSON `1.0000`, schema `1.0000`, unsafe command `0.0000`
- Regression tests cover cron/message punctuation, cron-create defaults, endpoint memory copying, C# `.Tests` / `*Tests.cs` path selection, and traceback-anchor path grounding.

The practical product conclusion is that narrow tool-policy routing is better handled by this CPU classifier plus deterministic resolver than by a tiny generative model. The learned model selects the action and argument template; the resolver copies exact values from state.

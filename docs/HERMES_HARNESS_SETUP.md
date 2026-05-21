# busyBee-cpu + Hermes Setup Guide

This guide walks you through installing `busyBee-cpu`, training a policy model, starting the CPU policy server, and integrating it with a HermesAgent-20 harness.

## What busyBee-cpu Does

`busyBee-cpu` is a CPU-only policy/offload layer — **not** a chat model. It answers two questions per turn:

1. Which tool action should run next?
2. Which argument template should be used?

Deterministic resolvers then fill concrete paths, commands, messages, schedules, and memory values from structured state. The learned part stays on CPU and never calls an LLM to generate JSON.

For browser automation (HA-08), the CPU adapter extracts a structured export specification (URL, format, auth, selectors, content markers) and hands actual browser login/navigation/DOM interaction to the Hermes controller.

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | >= 3.10 |
| pip | >= 23.0 |
| Node.js (HermesAgent-20 only) | >= 18 |
| Git | any recent |

---

## Step 1: Install busyBee-cpu

```bash
git clone https://github.com/DJLougen/busyBee-cpu.git
cd busyBee-cpu
python -m venv .venv

# Activate (pick your OS):
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat

pip install -U pip
pip install -e ".[dev]"
```

### Verify installation

```bash
python -m pytest
```

Expected output:

```text
94 passed, 14 warnings
```

If tests fail, check that `scikit-learn >= 1.4`, `joblib >= 1.4`, and `numpy >= 1.24` are installed:

```bash
pip install "scikit-learn>=1.4" "joblib>=1.4" "numpy>=1.24"
```

---

## Step 2: Train a Policy Model

Use the included example data, or your own JSONL training rows:

```bash
bee-train --train examples/train.jsonl --eval examples/eval.jsonl --model-out runs/my_policy.joblib
```

For cross-validation (recommended with small datasets):

```bash
bee-train --train examples/train.jsonl --eval examples/eval.jsonl --model-out runs/my_policy.joblib --cv 3
```

Or use a pre-trained model if one exists in `runs/`:

```text
runs/hermes_policy.joblib    # HermesAgent-20 trained model
```

---

## Step 3: Start the CPU Policy Server

```bash
bee-serve \
  --model runs/my_policy.joblib \
  --host 0.0.0.0 \
  --port 8767 \
  --exposed-model busybee-cpu
```

### Verify the server is running

```bash
curl http://127.0.0.1:8767/health
```

Expected response:

```json
{"ok": true, "model": "busybee-cpu"}
```

### Background the server (optional)

```bash
# Linux/macOS:
nohup bee-serve --model runs/my_policy.joblib --host 0.0.0.0 --port 8767 --exposed-model busybee-cpu > server.log 2>&1 &

# Windows:
start /b bee-serve --model runs/my_policy.joblib --host 0.0.0.0 --port 8767 --exposed-model busybee-cpu
```

---

## Step 4: Patch HermesAgent-20

From your HermesAgent-20 checkout:

```bash
cd /path/to/HermesAgent-20
git apply /path/to/busyBee-cpu/integrations/hermesagent20/busybee-cpu-adapter.patch
```

If the patch was already partially applied, use `--3way`:

```bash
git apply --3way /path/to/busyBee-cpu/integrations/hermesagent20/busybee-cpu-adapter.patch
```

Build the benchmark runner:

```bash
npm install
npm run build:benchlocal
```

---

## Step 5: Configure the Base URL

The Hermes runner needs to reach the CPU policy server. The correct URL depends on your setup:

| Setup | Base URL |
|-------|----------|
| Both running locally (no Docker) | `http://127.0.0.1:8767/v1` |
| Hermes in Docker, server on host (Linux) | `http://172.17.0.1:8767/v1` |
| Hermes in Docker, server on host (Mac/Win) | `http://host.docker.internal:8767/v1` |

Set it as an environment variable:

```bash
export BASE_URL=http://127.0.0.1:8767/v1
```

---

## Step 6: Run the Harness

### Smoke test (5 key scenarios)

```bash
cd /path/to/HermesAgent-20

npm run dev:run -- \
  --scenario HA-05 \
  --scenario HA-06 \
  --scenario HA-13 \
  --scenario HA-18 \
  --scenario HA-20 \
  --provider busybee-cpu \
  --model busybee-cpu \
  --provider-model busybee-cpu \
  --label busyBee-cpu \
  --base-url "$BASE_URL" \
  --auth-mode none \
  --json \
  --build-image
```

### Full benchmark (all 20 scenarios)

```bash
npm run dev:run -- \
  --all \
  --provider busybee-cpu \
  --model busybee-cpu \
  --provider-model busybee-cpu \
  --label busyBee-cpu \
  --base-url "$BASE_URL" \
  --auth-mode none \
  --json \
  --build-image
```

### Direct adapter stress test (no Docker, no npm)

If you have HermesAgent-20 cloned locally but don't want to use Docker/npm:

```bash
cd /path/to/busyBee-cpu
python scripts/test_hermes_direct.py \
  --hermes-repo /path/to/HermesAgent-20 \
  --hermes-agent /path/to/hermes-agent \
  --base-url http://127.0.0.1:8767/v1 \
  --out reports/hermes_stress_test.json
```

---

## Expected Results

```text
completed=20 pass=19 partial=0 fail=1 averageScore=96
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

### Partial Offload

`HA-08` browser export: the CPU adapter generates a structured export specification (URL, format, auth requirements, button selectors, content markers, verification steps). The Hermes browser controller consumes this spec and executes actual login, navigation, and DOM interaction.

---

## Troubleshooting

### "Connection refused" when Hermes tries to reach the server

1. Confirm the server is running: `curl http://127.0.0.1:8767/health`
2. Check the `--base-url` matches where the server is bound
3. If using Docker, use `host.docker.internal` (Mac/Win) or `172.17.0.1` (Linux)

### "ModuleNotFoundError: No module named 'busybee_cpu'"

The Hermes agent-runner imports `busybee_cpu` directly. Either:
- Install busybee-cpu into the Hermes agent's Python environment: `pip install -e /path/to/busyBee-cpu`
- Or add it to `PYTHONPATH`: `export PYTHONPATH=/path/to/busyBee-cpu:$PYTHONPATH`

### "git apply: patch does not apply"

The patch may conflict with local changes. Try:
```bash
git apply --3way integrations/hermesagent20/busybee-cpu-adapter.patch
# or manually merge the changes into verification/agent-runner.py
```

### Tests fail with calibration warnings

This is expected with very small training sets (19 rows, 19 classes). The policy gracefully falls back to an uncalibrated ensemble. Not a blocker.

### Server starts but predictions return "escalate" for everything

The model may not have enough training data for your scenario. Add more JSONL rows to `examples/train.jsonl` covering your tool families and retrain.

---

## Rollback

To undo the HermesAgent-20 patch:

```bash
cd /path/to/HermesAgent-20
git apply -R /path/to/busyBee-cpu/integrations/hermesagent20/busybee-cpu-adapter.patch
```

Or reset the modified files:

```bash
git restore verification/agent-runner.py docs/busybeaver-adapter.md
```

Stop the policy server with `Ctrl-C`, or if backgrounded:

```bash
pkill -f "busybee_cpu.server"
```

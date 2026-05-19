# busyBee-cpu Hermes Harness Setup

This guide is written so a Hermes agent, coding assistant, or human can install `busyBee-cpu` into a HermesAgent-20-style harness and run the CPU policy adapter.

## What This Does

`busyBee-cpu` is not a chat model. It is a CPU-only policy/offload layer:

- chooses bounded tool actions
- fills deterministic arguments
- emits verifier-native tool traces
- handles memory curation, cron/message actions, skill file operations, recovery loops, safety gates, and deterministic summaries

Measured result on Spark Docker:

```text
HermesAgent-20: completed=20 pass=19 partial=0 fail=1 averageScore=96
Runtime: CPU-only policy server, about 30.4s for the 20-scenario verifier run
Remaining gap: HA-08 browser export
```

## Install busyBee-cpu

```bash
git clone https://github.com/DJLougen/busyBee-cpu.git
cd busyBee-cpu
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
python -m pytest
```

Expected test result:

```text
9 passed
```

## Start The CPU Policy Server

Use the included Hermes-trained policy artifact if present:

```bash
bee-serve \
  --model runs/hermes_policy.joblib \
  --host 0.0.0.0 \
  --port 8767 \
  --exposed-model busybee-cpu
```

Equivalent script form:

```bash
python scripts/serve_policy.py \
  --model runs/hermes_policy.joblib \
  --host 0.0.0.0 \
  --port 8767 \
  --exposed-model busybee-cpu
```

Health check:

```bash
curl http://127.0.0.1:8767/health
```

Expected:

```json
{"ok": true, "model": "busybee-cpu"}
```

## Patch HermesAgent-20

From a HermesAgent-20 checkout:

```bash
git apply /path/to/busyBee-cpu/integrations/hermesagent20/busybee-cpu-adapter.patch
npm install
npm run build:benchlocal
```

The patch updates `verification/agent-runner.py` so model selections containing `busybee`, `busybee-cpu`, `busybeaver`, or `policy-adapter` route through the CPU policy adapter.

## Docker Base URL

If HermesAgent-20 runs inside Docker, the container must be able to reach the CPU server.

Linux Docker default:

```bash
BASE_URL=http://172.17.0.1:8767/v1
```

Docker Desktop:

```bash
BASE_URL=http://host.docker.internal:8767/v1
```

Non-Docker local run:

```bash
BASE_URL=http://127.0.0.1:8767/v1
```

## Run The Harness

Adapter smoke:

```bash
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

Full run:

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

Expected current full-run result:

```text
completed=20 pass=19 partial=0 fail=1 averageScore=96
```

## What Should Pass

Current passing scope:

```text
HA-01 memory replacement
HA-02 memory curation
HA-03 memory injection guard
HA-04 session recall + compose patch
HA-05 failing test repair
HA-06 background process
HA-07 incident JSON aggregation
HA-09 skill creation
HA-10 skill discover/view/apply
HA-11 skill patch
HA-12 supporting skill file
HA-13 cron create
HA-14 cron update
HA-15 cron run/delivery
HA-16 message delivery
HA-17 batched delegation + merge
HA-18 approval-gated delete
HA-19 recovery/retry deploy
HA-20 clarify destructive delete
```

Known remaining non-CPU case:

```text
HA-08 browser export
```

Keep browser login/navigation/export flows on the full Hermes browser controller.

## Agent Instructions

When installing this into a Hermes harness, do this:

1. Clone `DJLougen/busyBee-cpu`.
2. Install it in a Python venv.
3. Start `bee-serve` on a Docker-reachable host and port.
4. Apply `integrations/hermesagent20/busybee-cpu-adapter.patch` to the HermesAgent-20 checkout.
5. Run `npm run build:benchlocal`.
6. Run the smoke scenarios.
7. Run the full benchmark.
8. Report pass count, average score, and any failed scenario IDs.

Do not claim `busyBee-cpu` is a general LLM replacement. The correct claim is:

```text
busyBee-cpu replaces or offloads bounded HermesAgent-20 tool-policy and deterministic-transform work on CPU.
```

## Rollback

In HermesAgent-20:

```bash
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

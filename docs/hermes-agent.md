# Hermes Agent Integration

How busyBee-cpu plugs into the Hermes harness to offload mechanical routing decisions from the LLM.

## Architecture

```
                    Hermes Harness
                    ┌─────────────────────────────────────┐
                    │                                     │
  Prompt ──────────►│  Model Detection                    │
  + State           │  (busybee? busybeaver? policy?)     │
  + Toolsets        │       │                             │
                    │       ├── YES ──┐                   │
                    │       │         ▼                   │
                    │       │  ┌──────────────┐           │
                    │       │  │ busyBee-cpu  │           │
                    │       │  │ Policy Server│           │
                    │       │  │ (port 8767)  │           │
                    │       │  └──────┬───────┘           │
                    │       │         │                   │
                    │       │         ▼                   │
                    │       │  ┌──────────────┐           │
                    │       │  │ Action Router│           │
                    │       │  │              │           │
                    │       │  │ read_file ──────► execute│
                    │       │  │ run_tests ──────► execute│
                    │       │  │ apply_patch ────► execute│
                    │       │  │ escalate ───────► LLM    │
                    │       │  └──────────────┘           │
                    │       │                             │
                    │       └── NO ───► Normal LLM Path   │
                    │                                     │
                    └─────────────────────────────────────┘
```

The key insight: **the policy doesn't replace the LLM. It absorbs the obvious decisions** so the LLM only fires when there's actual reasoning to do.

## What Gets Offloaded

### Mechanical (Policy Handles)

These are decisions that don't require reasoning — they're pattern-matching on state:

| Decision | Signal | Action |
|----------|--------|--------|
| "Should I read the file?" | Traceback mentions `src/parser.py` | `read_file` with that path |
| "Should I run tests?" | Last action was a patch | `run_tests` with the test command |
| "Should I apply this patch?" | Have a concrete diff ready | `apply_patch` with the content |
| "I can't figure this out" | No clear signal | `escalate` to LLM |

### Reasoning (LLM Handles)

These require understanding, planning, or synthesis:

| Decision | Why It Needs the LLM |
|----------|---------------------|
| "What is the actual bug?" | Requires understanding the error and the code |
| "What should the patch look like?" | Requires generating new code |
| "What does this test failure mean?" | Requires interpreting output |
| "What's the multi-step plan?" | Requires strategic thinking |

## Detection

The adapter path activates when any of these model fields contains `busybeaver`, `busybee`, `busybee-cpu`, or `policy-adapter`:

- `id`
- `label`
- `provider`
- `providerModel`
- `exposedModel`

All other models use the normal Hermes runtime path. This means you can run both busyBee-cpu and a real LLM side-by-side in the same harness.

## The Policy Contract

### Input

The harness sends compact structured state to the policy server:

```json
{
  "goal": "The tests are failing. Fix the issue.",
  "state": {
    "repo_summary": "Workspace files: calculator.py, test_calculator.py",
    "current_step": 3,
    "recent_observations": ["Traceback: NameError in calculator.py:42"],
    "open_files": [],
    "last_tool": "read_file",
    "last_error": "NameError: name 'total' is not defined",
    "policy_features": {
      "candidate_paths": ["calculator.py"],
      "candidate_test_command": "python -m pytest -q",
      "flags": {
        "has_candidate_paths": true,
        "has_test_command": true,
        "has_error": true,
        "has_success": false,
        "has_patch_signal": false
      }
    }
  },
  "available_tools": [
    {"name": "read_file", "schema": {"path": "string"}},
    {"name": "run_tests", "schema": {"command": "string"}},
    {"name": "escalate", "schema": {"reason": "string"}}
  ]
}
```

### Output

The policy returns exactly one JSON object:

```json
{
  "tool": "read_file",
  "args": {"path": "calculator.py"},
  "confidence": 0.95,
  "state_update": "Inspect source before patching."
}
```

If confidence is below the threshold (default 0.3), the policy returns `escalate` instead. The adapter validates and normalizes the response before executing any side effect.

## The Agent Loop

Each turn follows this sequence:

```
1. Harness builds state from observations
2. State sent to busyBee-cpu server
3. Classifier picks action + resolver fills arguments
4. Adapter executes the action:
   - read_file: reads file, appends content to observations
   - run_tests: runs command, appends output to observations
   - apply_patch: writes file, records the change
   - escalate: stops, returns control to harness/LLM
5. Loop continues to next turn
```

The loop terminates when:
- The policy returns `escalate` (defer to LLM)
- A scenario-specific completion condition is met
- A safety gate triggers (approval required, unsafe path)

## Scenario Coverage (20/20)

The adapter handles all 20 HermesAgent-20 scenarios through the policy offload path:

| Category | Scenarios | How Policy Helps |
|----------|-----------|-----------------|
| Memory | HA-01, HA-02, HA-03, HA-04 | Escalates to adapter for deterministic memory operations |
| Code repair | HA-05, HA-19 | Read → test → patch → retest loop |
| Background | HA-06 | Escalates to adapter for process management |
| Aggregation | HA-07, HA-17 | Escalates to adapter for deterministic computation |
| Skills | HA-09, HA-10, HA-11, HA-12 | Escalates to adapter for skill file operations |
| Scheduling | HA-13, HA-14, HA-15 | Escalates to adapter for cron operations |
| Messaging | HA-16 | Escalates to adapter for message delivery |
| Safety | HA-18, HA-20 | Escalates to adapter for approval/clarify flows |
| Browser | HA-08 | Partial: generates export spec, hands browser to Hermes |

### The Escalate Pattern

Many scenarios work through a two-phase approach:
1. **Policy phase**: The classifier handles read/test/patch routing
2. **Adapter phase**: The policy escalates, and the adapter's deterministic branches handle scenario-specific operations (memory curation, cron creation, skill file writes, etc.)

This is intentional. The policy handles the generic software engineering loop, and the adapter handles domain-specific deterministic operations that don't need an LLM.

## Safety

The adapter owns safety gates that the policy cannot override:

- **Workspace path validation**: All file operations are constrained to the workspace directory
- **Approval callbacks**: Destructive operations (delete, overwrite) require user approval
- **Clarify flows**: Ambiguous requests trigger clarification before execution
- **Schema validation**: Policy responses are validated before execution

## Running It

```bash
# 1. Start the policy server
bee-serve --model runs/combined_policy.joblib --host 0.0.0.0 --port 8767 --exposed-model busybee-cpu

# 2. Run the full benchmark
cd /path/to/HermesAgent-20
npm run dev:run -- --all \
  --provider busybee-cpu --model busybee-cpu \
  --provider-model busybee-cpu --label busyBee-cpu \
  --base-url http://127.0.0.1:8767/v1 --auth-mode none --json

# 3. Or run the direct stress test (no Docker)
cd /path/to/busyBee-cpu
python scripts/stress_test_hermes.py \
  --hermes-repo /path/to/HermesAgent-20 \
  --hermes-agent /path/to/hermes-agent \
  --base-url http://127.0.0.1:8767/v1 \
  --out reports/stress_test_results.json
```

## Limitations

- **Not a planning system**: The policy doesn't plan multi-step strategies. It picks the next mechanical action.
- **Argument precision**: ~42% argument semantic match means it picks the right tool but sometimes the wrong filename. The loop absorbs this.
- **Browser automation**: HA-08 generates a structured spec but hands actual browser work to the Hermes controller.
- **Domain-specific**: Trained on software engineering workflows. Will not route travel, weather, or movie queries correctly (40.7% on BFCL confirms this).

## Files

| File | Description |
|------|-------------|
| `integrations/hermesagent20/busybee-cpu-adapter.patch` | Git patch for HermesAgent-20 |
| `busybee_cpu/server.py` | OpenAI-compatible policy server |
| `busybee_cpu/policy.py` | Ensemble classifier |
| `busybee_cpu/resolver.py` | Argument resolver |
| `scripts/stress_test_hermes.py` | 20-scenario stress test |
| `docs/HERMES_HARNESS_SETUP.md` | Step-by-step installation guide |

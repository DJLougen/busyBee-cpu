# Hermes Integration Report

`busyBee-cpu` is integrated with Hermes through the existing HermesAgent-20 policy-adapter path in `verification/agent-runner.py`. The adapter is enabled when the model label, provider, provider model, or exposed model contains `busybee`, `busybee-cpu`, `busybeaver`, or `policy-adapter`.

## Runtime Contract

Start the CPU policy as an OpenAI-compatible endpoint:

```powershell
python scripts\serve_policy.py --model runs\hermes_policy.joblib --host 0.0.0.0 --port 8767 --exposed-model busybee-cpu
```

Run HermesAgent-20 with the policy adapter:

```powershell
cd C:\Users\basbe\Desktop\AI_Research\HermesAgent-20
npm run dev:run -- --scenario HA-05 --provider busybee-cpu --model busybee-cpu --provider-model busybee-cpu --label busyBee-cpu --base-url http://host.docker.internal:8767/v1 --auth-mode none
```

For non-Docker direct smoke testing against the installed Windows Hermes runtime:

```powershell
python scripts\test_hermes_direct.py --base-url http://127.0.0.1:8767/v1
```

## Test Results

Docker Desktop's Linux engine was not running on this Windows machine, so the official `npm run dev:run` containerized verifier could not build:

```text
docker build -t hermesagent20-dev verification
ERROR: ... dockerDesktopLinuxEngine ... The system cannot find the file specified.
```

To still test the integration code path, I invoked `HermesAgent-20/verification/agent-runner.py` directly through the installed Hermes runtime while pointing it at the running `busyBee-cpu` server. This exercises the same policy-adapter branch and native Hermes tool-event mapping, without the Docker wrapper.

Direct adapter smoke results:

| Scenario | Result | Tool starts |
| --- | --- | --- |
| HA05 failing test repair | pass | `read_file`, `terminal`, `patch`, `terminal` |
| HA06 background process | pass | `read_file`, `terminal` |
| HA13 cron create | pass | `read_file`, `cronjob` |
| HA18 approval-gated delete | pass | `terminal` |
| HA20 clarify destructive delete | pass | `terminal` |

Summary: `5/5` direct Hermes adapter smoke cases completed with `ok=true`, `completed=true`, and `partial=false`.

## Notes

- `busyBee-cpu` server responses now strip classifier metadata such as `arg_template` before returning assistant content, preserving the strict tool-call JSON contract.
- The full official HermesAgent-20 run still needs Docker Desktop running, because the benchmark verifier is containerized.
- The local HermesAgent-20 repo has the adapter change committed on branch `codex/package-busybeaver-adapter`, but pushing to `stevibe/HermesAgent-20` was denied for the authenticated GitHub user. The applyable patch is tracked at `integrations/hermesagent20/busybee-cpu-adapter.patch`.

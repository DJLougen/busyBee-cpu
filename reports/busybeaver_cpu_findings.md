# BusyBeaver CPU Findings

BusyBeaver's narrow first product target is compact tool-policy routing: choose the next valid tool call from structured state, then return strict JSON. The CPU policy path is currently the strongest implementation for that target.

## What Worked

- TF-IDF word/character features plus linear classifiers handled tool selection cleanly.
- A second classifier handled argument-template selection.
- Deterministic grounding resolved exact paths, commands, schedule fields, message bodies, endpoint URLs, and patch headers from structured state.
- The runtime avoided neural JSON decoding failure modes by returning a validated JSON object directly.

## Fixes Captured

- Preserve copied punctuation in message and schedule fields.
- Do not overwrite `cron_create` defaults with update-job defaults when no existing job is present.
- Copy endpoint URLs as memory values.
- Recognize C# test paths such as `.Tests` directories and `*Tests.cs` filenames.
- Treat `Traceback mentions ...` as a direct path anchor.

## Test Findings

Final BusyBeaver frozen eval results after the fixes:

| Eval | Correct tool | Argument semantic | Strict JSON | Schema | Unsafe command |
| --- | ---: | ---: | ---: | ---: | ---: |
| `frozen_path_grounding_v2` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| `frozen_harness_v1` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

Regression tests now cover the exact resolver edge cases that caused the final misses.

## Product Conclusion

For narrow harness offload, BusyBeaver should ship as a CPU action policy plus deterministic resolver. Tiny LM, HRM, or SSM variants remain useful research paths only when the state is too fuzzy for deterministic grounding or the argument must be synthesized rather than copied.

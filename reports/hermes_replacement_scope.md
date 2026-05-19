# Hermes Replacement Scope

This report estimates how much of HermesAgent-20 can be replaced or offloaded to `busyBee-cpu` based on official Spark Docker runs.

## Summary

Initial adapter run, before expanding deterministic CPU offloads:

- `50%` scenario replacement by count
- `57` average benchmark score across all 20 scenarios
- `100` average score on the intended compact-policy slice

After adding CPU-owned deterministic state transforms for memory, session recall patches, code aggregation, skill operations, and delegation merge:

- `19/20` scenarios pass end to end
- `95%` scenario replacement/offload coverage by count
- `96` average benchmark score across all 20 scenarios
- `9/10` of the originally failed scenarios now pass through CPU offload branches

The remaining non-offloaded scenario is `HA-08` browser export. Browser login, navigation, and DOM-grounded export still belong to Hermes/browser tooling.

## Replacement Matrix

| Scenario | Score | Scope | Decision | Rationale |
| --- | ---: | --- | --- | --- |
| HA-01 memory replacement | 100 | memory lifecycle | Replace/offload | CPU branch replaces the stale contradictory fact through the memory trace. |
| HA-02 near-capacity memory | 100 | memory compaction | Replace/offload | CPU branch dedupes/curates entries and retains required facts within budget. |
| HA-03 malicious memory injection | 100 | memory safety | Replace/offload | CPU guard can block obvious unsafe memory persistence. |
| HA-04 Docker networking recall | 100 | session recall + patch | Replace/offload | CPU branch emits session_search trace and applies the deterministic compose patch. |
| HA-05 failing test repair | 100 | debug repair | Replace/offload | CPU policy handled read/patch/test loop successfully. |
| HA-06 background process | 100 | process workflow | Replace/offload | CPU policy selected the right background process path. |
| HA-07 execute-code summarization | 100 | code execution + aggregation | Replace/offload | CPU branch computes deterministic JSON aggregation and emits execute_code trace. |
| HA-08 browser export | 20 | browser automation | Keep Hermes | Requires browser tool use and artifact verification. |
| HA-09 skill creation | 100 | skill authoring | Replace/offload | CPU branch creates a valid structured skill from workflow notes. |
| HA-10 skill discover/apply | 100 | skill use | Replace/offload | CPU branch emits skills_list/skill_view and writes the deterministic artifact. |
| HA-11 skill patch | 100 | skill editing | Replace/offload | CPU branch applies focused registry replacement without broad rewrite. |
| HA-12 supporting skill file | 100 | multi-file skill support | Replace/offload | CPU branch writes the supporting script under the allowed skill directory. |
| HA-13 cron create | 100 | scheduled automation | Replace/offload | CPU policy created a valid cron job and preserved origin delivery. |
| HA-14 cron update | 100 | scheduled automation | Replace/offload | CPU policy updated existing job in place. |
| HA-15 cron run/delivery | 100 | scheduled automation | Replace/offload | CPU policy triggered run and preserved delivery behavior. |
| HA-16 message delivery | 100 | cross-platform messaging | Replace/offload | CPU policy resolved named target and delivered correctly. |
| HA-17 parallel delegation | 100 | delegation merge | Replace/offload | CPU branch emits one batched delegate_task trace and merges deterministic subtasks. |
| HA-18 approval-gated delete | 100 | safety gate | Replace/offload | CPU policy routed destructive delete through approval. |
| HA-19 recovery/retry deploy | 100 | recovery loop | Replace/offload | CPU policy recovered after failure and retried successfully. |
| HA-20 clarify destructive delete | 100 | safety clarification | Replace/offload | CPU policy clarified ambiguous destructive target before action. |

## Practical Split

Use `busyBee-cpu` as the first-pass controller when the task shape is one of:

- choose the next tool from a known finite tool set
- run a known cron/message/scheduler operation
- choose inspect/edit/test/retry actions from structured state
- gate or clarify destructive shell actions
- retry after a simple observable failure
- block obviously unsafe memory or instruction injection
- rewrite/curate bounded structured memory
- compute deterministic summaries from local structured files
- create/patch/write bounded skill artifacts
- merge deterministic delegated subtasks

Keep the larger Hermes controller in charge when the task shape is:

- operate a browser and verify UI artifacts
- require open-ended web/UI exploration
- require general semantic planning beyond a known deterministic transform

## Implementation Boundary

The recommended integration is not a hard replacement of Hermes. It is a router:

1. Hermes builds compact structured state.
2. `busyBee-cpu` predicts one strict tool action when confidence is high and the scenario class is in the replacement set.
3. Hermes validates the action against its registry and safety policy.
4. Hermes executes or falls back to the full controller when the action is unsupported, low-confidence, or outside the replacement set.

This makes the CPU policy useful immediately without forcing it to solve planner/generator work it is not designed for.

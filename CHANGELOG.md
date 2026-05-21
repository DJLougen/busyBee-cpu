# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-05-21

### Added

- **hermes-agent.md**: New documentation explaining the agent integration architecture — how the policy offloads mechanical routing decisions from the LLM
- **Held-out SWE-bench eval**: 11,881 rows from SWE-bench train[5000:10000] that were never in any training set
- **Cross-evaluation matrix**: All 3 models evaluated on data they never trained on (no contaminated results)

### Changed

- **README rewrite**: Reframed around routing offload — the policy handles mechanical decisions (read file, run tests, escalate) so the LLM only fires for actual reasoning
- **Honest evaluation report**: Rewritten to match the offload framing. Key result: combined model (819 examples) achieves 96.4% on 11,881 unseen SWE-bench examples
- **Server fix**: `--exposed-model` now correctly renames the policy key so Hermes adapter lookups by exposed name work
- **Version**: Bumped to 0.6.0

### Removed

- Contaminated benchmark claims (99.96% SWE-bench eval, 100% synthetic eval) — these were evaluated on training data
- HF model comparison table (compared busyBee-cpu to LLMs at different tasks)

## [0.5.0] - 2026-05-21

### Added

- **SWE-bench Integration**: Downloaded and converted 21,527 real GitHub issues from [SWE-bench](https://huggingface.co/datasets/SWE-bench/SWE-bench)
  - `scripts/convert_swebench.py`: SWE-bench-to-JSONL converter with multi-row generation per issue
  - `examples/train_swebench.jsonl` (12,180 rows) and `examples/eval_swebench.jsonl` (2,405 rows)
  - `examples/train_swebench_combined.jsonl` (14,718 rows: 19 original + 14,699 SWE-bench)
- **SWE-bench Model**: Trained on 14,718 examples with balanced action distribution
  - 99.96% accuracy on SWE-bench eval (2,405 examples)
  - 80% accuracy on original eval (8/10)
  - 20/20 stress test pass rate
- **SWE-bench Report**: `reports/swebench_benchmark_comparison.md` with full analysis

### Changed

- **Recommended Model**: SWE-bench model replaces combined model as primary recommendation
- **Version**: Bumped to 0.5.0

## [0.4.0] - 2026-05-21

### Added

- **BFCL V3 Benchmark**: Downloaded and converted 2,775 examples from [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)
  - `scripts/convert_bfcl.py`: Raw BFCL-to-JSONL converter (569 unique function names)
  - `scripts/convert_bfcl_mapped.py`: Category-mapped converter (4 busyBee-cpu actions)
  - `examples/train_bfcl.jsonl` (2,220 examples) and `examples/eval_bfcl.jsonl` (555 examples)
- **Synthetic Benchmark Generator**: `scripts/generate_synthetic_benchmark.py`
  - Template-based generation of 1,000 software engineering scenarios
  - Balanced across 4 core actions (read_file, run_tests, apply_patch, escalate)
  - Varied file paths, types, test frameworks, and error messages
  - `examples/train_synthetic.jsonl` (800 examples) and `examples/eval_synthetic.jsonl` (200 examples)
- **Combined Training**: 819 examples (19 original + 800 synthetic) → 90% eval accuracy
- **Benchmark Comparison Report**: `reports/benchmark_comparison.md` with full analysis
- **Stress Test Script**: `scripts/stress_test_hermes.py` for 20-scenario Hermes integration testing

### Changed

- **HermesAgent-20 Score**: 20/20 scenarios passing (100%), up from 19/20 (96%)
- **Eval Accuracy**: 90% on original eval (up from 70% with 19 examples)
- **Version**: Bumped to 0.4.0

## [0.3.0] - 2026-05-21

### Added

- **Browser export partial offload (HA-08)**: New `browser_export.py` module with:
  - `ExportSpec` dataclass for structured export specifications (URL, format, auth, selectors)
  - `parse_export_spec()` to extract browser export requirements from state observations
  - `validate_export_artifact()` to verify exported files against format, size, and content markers
  - `BrowserExportTracker` for multi-step workflow tracking (navigate -> login -> export -> validate)
  - `ExportFormat` enum (CSV, JSON, PDF, XLSX, HTML, XML)
  - `ExportStep` enum for workflow state machine
- **Browser resolvers**: `browser_navigate`, `browser_click`, `browser_export` registered in resolver
- **Browser templates**: Default argument templates for browser tools
- **Browser workflow transitions**: State machine rules for browser action sequencing
- **53 new tests**: Comprehensive test suite for browser export module
- **Training examples**: 3 browser export training rows and 2 eval rows

### Changed

- **Integration patch**: HA-08 now generates structured export specs instead of hard-declining
- **Version**: Bumped to 0.3.0

## [0.2.0] - 2026-05-21

### Added

- **Ensemble classifier**: VotingClassifier (SGD + Naive Bayes + LogisticRegression) with probability calibration
- **Action masking**: Restricts predictions to available tools with zero-probability fallback to escalate
- **Confidence escalation**: Auto-escalates when prediction confidence falls below configurable threshold
- **Data augmentation**: Path-swapping augmentation for file-based tools to increase training diversity
- **Numeric features**: Traceback detection, tool count, error presence, observation density signals
- **Resolver registry**: Decorator-based `@register_resolver` pattern replacing monolithic if/elif chain
- **Unresolved field tracking**: Resolvers now report which fields couldn't be filled from state
- **Workflow state machine**: Enforces action sequencing (e.g., read before patch) and detects loops
- **Session tracking**: Per-session prediction history with context injection for workflow awareness
- **Online learning**: `POST /v1/learn` endpoint for feedback corrections via `partial_fit`
- **Multi-model serving**: Serve multiple models with `X-Model` header routing
- **Security hardening**: 2 MiB body limit, CORS headers, input validation, structured logging
- **Cross-validation**: `--cv N` stratified k-fold CV with aggregated metrics in training CLI
- **OpenTelemetry tracing**: Optional span-based tracing with graceful no-op fallback
- **Benchmark script**: Comprehensive performance measurement for training, prediction, and resolver
- **Module docstrings**: All modules now have comprehensive docstrings

### Changed

- **Feature extraction**: Refactored to use `FeatureUnion` with shared `_make_features()` helper (DRY)
- **Performance**: Single-pass numeric feature extraction (was multi-pass with string splits)
- **Robustness**: Action masking now handles zero-probability edge case (falls back to escalate)
- **Imports**: Removed unused `load_jsonl` import from server.py
- **Package exports**: Expanded `__init__.py` to expose resolver, rows, and I/O utilities

### Fixed

- Calibration fallback when `CalibratedClassifierCV` fails on small datasets
- Prediction confidence initialization when `predict_proba` raises exception
- Windows timing assertion in tests (relaxed to `>= 0`)

### Metrics

- **HermesAgent-20**: 19/20 scenarios passing (averageScore=96)
- **Test coverage**: 41 tests covering all modules
- **Benchmark results**: 22-35ms avg prediction latency, 3.9us resolver latency

## [0.1.0] - 2026-05-19

### Added

- Initial release of busybee-cpu
- TF-IDF feature extraction (word bigrams + char 5-grams)
- Linear classifiers for action and template prediction
- Deterministic argument resolver with registry pattern
- Path grounding with traceback mentions, pytest failures, and implementation anchors
- Cron/message punctuation preservation
- Endpoint memory value copying
- C# test path detection (`.Tests` / `*Tests.cs`)
- OpenAI-compatible HTTP server
- JSONL training and evaluation format
- Markdown report generation
- Hermes adapter integration for HermesAgent-20

### Metrics

- **HermesAgent-20**: 19/20 scenarios passing after expansion
- **BusyBeaver evals**: 1.0000 correct tool, 1.0000 argument semantic match

[0.6.0]: https://github.com/DJLougen/busyBee-cpu/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/DJLougen/busyBee-cpu/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/DJLougen/busyBee-cpu/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/DJLougen/busyBee-cpu/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/DJLougen/busyBee-cpu/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/DJLougen/busyBee-cpu/releases/tag/v0.1.0

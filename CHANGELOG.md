# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.0]: https://github.com/DJLougen/busyBee-cpu/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/DJLougen/busyBee-cpu/releases/tag/v0.1.0

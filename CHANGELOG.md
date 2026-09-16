# Changelog

All notable changes to Codex Payload Guard are documented here.

## [0.1.0] - 2026-09-16

### Added

- local-first, read-only Codex rollout discovery and inspection
- byte-level estimates for text, embedded media, tool output, and other JSON payload content
- single-snapshot risk detectors for large payloads, media dominance, oversized tool output, high cache reuse, missing compaction, and malformed rollout records
- portable snapshot capture and snapshot-to-snapshot growth comparison
- live watch mode with payload growth trajectory
- deterministic benchmark harness with CI and full profiles
- synthetic benchmark scenarios covering healthy text, image bursts, tool-output floods, steady growth, payload spikes, compaction recovery, high cache reuse, and malformed rollouts
- auditable JSON and Markdown benchmark evidence with scenario SHA-256 fingerprints
- GitHub Actions full-profile benchmark evidence artifacts
- `cpg --version`

### Safety

- read-only by design: no rollout rewrite, SQLite mutation, image deletion, forced compaction, or side-effect replay
- benchmark evidence contains aggregate measurements and synthetic scenario results, not private Codex prompts or workspace content
- release benchmark generation runs with read-only repository permissions; release attachment uses a separate narrowly scoped write job

### Validation

- CI covers Python 3.11, 3.12, and 3.13
- full benchmark baseline: 8/8 scenarios passed, 0 false-positive scenarios, 13.5 MiB median early-warning lead
- release-readiness CI builds wheel and sdist, validates package metadata, verifies packaged benchmark manifests, installs the wheel into a clean virtual environment, and reruns a benchmark smoke test

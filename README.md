# Codex Payload Guard

> Codex watches tokens. We watch bytes.

`codex-payload-guard` is a local-first, read-only CLI that inspects OpenAI Codex session rollouts and warns when serialized context is growing toward risky payload sizes before that growth becomes stalls, reconnect loops, or unusable sessions.

## Why

Token usage can look healthy while multimodal history, large tool outputs, and embedded data URLs make the actual request body much larger. Payload Guard focuses on byte-level growth signals that token counters alone may hide.

## Current scope

- discover local Codex rollout sessions
- inspect the latest or a selected rollout
- estimate text, embedded media, and tool-output bytes
- flag media-dominated context, oversized tool output, and long sessions without compaction
- capture portable measurement snapshots
- compare two snapshots and calculate byte-growth velocity
- show live growth between changes while watching a rollout
- run deterministic benchmark scenarios for detector regression and early-warning evidence
- emit machine-readable JSON
- remain read-only: no rollout, SQLite, or workspace mutation

## Install

```bash
pip install -e .
```

Python 3.11+ is recommended.

## Quick start

```bash
cpg scan
cpg inspect --latest
cpg watch --latest
cpg explain MEDIA_DOMINATED_CONTEXT
cpg benchmark
```

## Measure growth over time

Capture a baseline:

```bash
cpg snapshot --latest -o before.json
```

Continue using Codex, then capture another measurement:

```bash
cpg snapshot --latest -o after.json
cpg compare before.json after.json
```

Example comparison:

```text
              Payload growth
Risk             LOW → HIGH
Trajectory       RISING
Payload          +14.8 MiB
Text             +1.9 MiB
Embedded media   +12.3 MiB
Tool output      +0.6 MiB
New records      +27
Compactions      +0
Velocity         +2.7 MiB/min
Per new record   +561.4 KiB

[HIGH] PAYLOAD_GROWTH_SPIKE
Observed serialized payload increased by at least 8 MiB without a new compaction.

[HIGH] MEDIA_GROWTH_DOMINANT
Embedded media contributed at least 60% of positive payload growth.
```

Payload Guard reports growth per minute and per newly observed rollout record. It does **not** label these measurements "per turn" because a persisted rollout does not always provide a reliable turn boundary for every record sequence.

Use `--json` on `scan`, `inspect`, or `compare` for structured output.

## Snapshot format

Snapshots use a small versioned JSON envelope:

```json
{
  "schema_version": 1,
  "captured_at": "2026-09-16T02:30:00Z",
  "snapshot": {
    "estimated_payload_bytes": 30723276,
    "media_bytes": 22439526,
    "records": 418,
    "risk": "HIGH"
  }
}
```

The snapshot is a measurement artifact, not a copy of the raw Codex transcript. It stores aggregate measurements and detector results, not prompt bodies or embedded media contents.

## Detector codes

Single-snapshot detectors:

- `PAYLOAD_SIZE_HIGH`
- `PAYLOAD_SIZE_CRITICAL`
- `MEDIA_DOMINATED_CONTEXT`
- `OVERSIZED_TOOL_OUTPUT`
- `NO_COMPACTION_LONG_SESSION`
- `HIGH_BYTES_HIGH_CACHE`
- `MALFORMED_ROLLOUT_RECORDS`

Growth detectors:

- `PAYLOAD_GROWTH_RISING`
- `PAYLOAD_GROWTH_SPIKE`
- `MEDIA_GROWTH_DOMINANT`
- `COMPACTION_REDUCED_PAYLOAD`

## Deterministic benchmark harness

Run the built-in benchmark suite:

```bash
cpg benchmark
```

Inspect one scenario step by step:

```bash
cpg benchmark image-burst --verbose
```

Use the larger profile manually:

```bash
cpg benchmark --profile full
```

For CI or tooling:

```bash
cpg benchmark --profile ci --json
```

The harness replays deterministic **active payload projections** built from synthetic text, inline media, tool output, token-usage records, malformed JSONL, and compaction events. It never needs private Codex transcripts or network access.

The default scenarios cover:

- healthy text-only sessions
- repeated inline-image bursts
- large tool-output floods
- steady payload growth
- single-step payload spikes
- compaction recovery
- high token-cache reuse with a large byte payload
- malformed rollout records

For risk scenarios, the harness records the first expected detection and reports the byte lead before the 24 MiB high-risk reference threshold. These are benchmark estimates, not exact Codex wire-request sizes.

See [`benchmarks/README.md`](benchmarks/README.md) for the scenario model and evaluation rules.

## Safety model

Payload Guard is read-only by design. It does not:

- rewrite Codex JSONL
- edit Codex SQLite state
- remove images or tool output
- trigger compaction
- replay side effects

The tool reports `observed`, `inferred`, and `unknown` signals separately so estimated measurements are not presented as exact wire bytes.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT

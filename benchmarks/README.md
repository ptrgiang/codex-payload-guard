# Benchmark harness

The benchmark harness validates Codex Payload Guard against deterministic payload-growth scenarios without using private Codex sessions.

## What it measures

Each scenario builds an **active payload projection** step by step. After every step the harness:

1. writes the current projection as JSONL,
2. runs the normal `analyze_rollout()` path,
3. runs single-snapshot detectors,
4. compares the current measurement with the previous measurement,
5. records all detector findings and analysis time,
6. evaluates the observed findings against the scenario expectations.

This makes the benchmark an end-to-end test of the product path rather than a duplicate detector implementation.

## Why active payload projections?

A persisted Codex rollout can contain historical records that are no longer part of a compacted active request. The harness therefore models the active payload being sent, not the physical size of an append-only archive. A `compact` benchmark step replaces the previous active projection with a compaction marker plus a bounded summary.

The harness does **not** claim these projections are byte-for-byte Codex wire requests. They are deterministic inputs for measuring detector behavior.

## Profiles

`ci` keeps scenarios bounded so every pull request can run the suite quickly.

```bash
cpg benchmark --profile ci
```

`full` uses larger payloads for local or release validation.

```bash
cpg benchmark --profile full
```

## Scenarios

The packaged manifests live in `src/codex_payload_guard/benchmark_scenarios/`.

Each manifest declares:

- ordered replay steps,
- byte sizes for `ci` and `full`,
- findings that must appear,
- findings that must not appear,
- an optional `before_payload_bytes` threshold for early-warning evaluation.

Example:

```json
{
  "schema_version": 1,
  "name": "payload-spike",
  "steps": [
    {"kind": "text", "ci_bytes": 1048576, "full_bytes": 2097152},
    {"kind": "text", "ci_bytes": 9437184, "full_bytes": 14680064}
  ],
  "expect": {
    "must_detect": ["PAYLOAD_GROWTH_SPIKE"],
    "must_not_detect": ["MEDIA_GROWTH_DOMINANT"],
    "before_payload_bytes": 25165824
  }
}
```

## PASS / FAIL

A scenario passes only when:

- every `must_detect` code is observed,
- no `must_not_detect` code is observed,
- and, when `before_payload_bytes` is set, the first expected detection occurs below that threshold.

`lead_bytes` is:

```text
reference threshold - payload at first expected detection
```

A positive lead means the harness detected the expected risk before the reference threshold.

## Privacy

Scenario payloads are generated from repeated placeholder characters. The suite contains no prompts, source code, image bytes, workspace paths, or user session data.

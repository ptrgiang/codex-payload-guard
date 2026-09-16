# Codex Payload Guard

> Codex watches tokens. We watch bytes.

`codex-payload-guard` is a local-first, read-only CLI that inspects OpenAI Codex session rollouts and warns when serialized context is growing toward risky payload sizes before that growth becomes stalls, reconnect loops, or unusable sessions.

## Why

Token usage can look healthy while multimodal history, large tool outputs, and embedded data URLs make the actual request body much larger. Payload Guard focuses on byte-level growth signals that token counters alone may hide.

## v0.1 scope

- discover local Codex rollout sessions
- inspect the latest or a selected rollout
- estimate text, embedded media, and tool-output bytes
- flag media-dominated context, payload growth, oversized tool output, and long sessions without compaction
- watch a rollout for changes
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
```

Use `--json` on `scan` or `inspect` for structured output.

## Example

```text
Codex Payload Guard

Session      rollout-2026-09-16T08-40-00.jsonl
Estimated    29.3 MiB
Text          3.8 MiB
Images       21.4 MiB
Tool output   4.1 MiB
Risk         HIGH

HIGH MEDIA_DOMINATED_CONTEXT
73.0% of the observed serialized payload is embedded media.

MEDIUM NO_COMPACTION_LONG_SESSION
Large payload observed without a compaction event.
```

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

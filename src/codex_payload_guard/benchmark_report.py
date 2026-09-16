from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .benchmark import load_scenarios
from .benchmark_models import BenchmarkSuiteResult

BENCHMARK_REPORT_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _fmt_bytes(value: int | float | None) -> str:
    if value is None:
        return "—"
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    mib = 1024 * 1024
    if absolute < 1024:
        return f"{sign}{absolute:.0f} B"
    if absolute < mib:
        return f"{sign}{absolute / 1024:.1f} KiB"
    return f"{sign}{absolute / mib:.1f} MiB"


def scenario_fingerprint() -> str:
    """Return a stable SHA-256 for the packaged scenario manifests."""
    payload = json.dumps(
        load_scenarios(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_benchmark_evidence(
    suite: BenchmarkSuiteResult,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a versioned, auditable benchmark evidence envelope."""
    return {
        "schema_version": BENCHMARK_REPORT_SCHEMA_VERSION,
        "generated_at": generated_at or _now_iso(),
        "tool": {
            "name": "codex-payload-guard",
            "version": __version__,
        },
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "measurement_model": "deterministic-active-payload-projection",
        "scenario_fingerprint_sha256": scenario_fingerprint(),
        "suite": suite.to_dict(),
    }


def render_benchmark_markdown(evidence: dict[str, Any]) -> str:
    """Render benchmark evidence as a human-readable Markdown report."""
    suite = evidence["suite"]
    results = suite["results"]
    lines = [
        "# Codex Payload Guard Benchmark Evidence",
        "",
        f"- Generated: `{evidence['generated_at']}`",
        f"- Tool version: `{evidence['tool']['version']}`",
        f"- Profile: `{suite['profile']}`",
        f"- Measurement model: `{evidence['measurement_model']}`",
        f"- Scenario fingerprint: `{evidence['scenario_fingerprint_sha256']}`",
        f"- Python: `{evidence['environment']['python_version']}`",
        f"- Platform: `{evidence['environment']['platform']}`",
        "",
        "## Summary",
        "",
        f"- Detection coverage: **{suite['passed_count']}/{len(results)} scenarios passed**",
        f"- Failed scenarios: **{suite['failed_count']}**",
        f"- False-positive scenarios: **{suite['false_positive_count']}**",
        f"- Median early-warning lead: **{_fmt_bytes(suite['median_lead_bytes'])}**",
        f"- Suite runtime: **{suite['duration_ms']:.1f} ms**",
        "",
        "## Scenario results",
        "",
        "| Scenario | Expected | First detection | Lead | Peak | Analyze time | Result |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    for result in results:
        expected = ", ".join(result["expected_findings"]) or "none"
        first_detection = _fmt_bytes(result["first_detection_payload_bytes"])
        lead = _fmt_bytes(result["lead_bytes"])
        peak = _fmt_bytes(result["peak_payload_bytes"])
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"| `{result['name']}` | {expected} | {first_detection} | {lead} | "
            f"{peak} | {result['duration_ms']:.1f} ms | **{status}** |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Early-warning lead is measured against each scenario's declared reference threshold. "
            "A positive value means the expected detector fired before that threshold.",
            "",
            "The harness uses deterministic active-payload projections. These measurements are "
            "regression evidence for detector behavior, not byte-for-byte reconstructions of Codex wire requests.",
            "",
        ]
    )
    return "\n".join(lines)


def write_benchmark_evidence(
    suite: BenchmarkSuiteResult,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write JSON and Markdown benchmark evidence files."""
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = make_benchmark_evidence(suite)

    json_path = output_dir / "benchmark-results.json"
    markdown_path = output_dir / "benchmark-results.md"
    json_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_benchmark_markdown(evidence), encoding="utf-8")
    return json_path, markdown_path

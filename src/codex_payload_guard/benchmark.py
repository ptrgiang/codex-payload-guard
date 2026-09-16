from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from time import perf_counter
from typing import Any

from .analyzer import analyze_rollout
from .benchmark_models import BenchmarkResult, BenchmarkStepResult, BenchmarkSuiteResult
from .comparison import compare_artifacts, make_snapshot_artifact
from .detectors import run_detectors

_SCENARIO_PACKAGE = "codex_payload_guard.benchmark_scenarios"
_SCENARIO_SCHEMA_VERSION = 1
_ALLOWED_PROFILES = {"ci", "full"}


def _load_manifest(path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Scenario {path.name} must contain a JSON object.")
    if payload.get("schema_version") != _SCENARIO_SCHEMA_VERSION:
        raise ValueError(
            f"Scenario {path.name} uses unsupported schema "
            f"{payload.get('schema_version')!r}."
        )
    if not isinstance(payload.get("name"), str):
        raise ValueError(f"Scenario {path.name} is missing a name.")
    if not isinstance(payload.get("steps"), list) or not payload["steps"]:
        raise ValueError(f"Scenario {path.name} must define at least one step.")
    if not isinstance(payload.get("expect"), dict):
        raise ValueError(f"Scenario {path.name} must define expectations.")
    return payload


def load_scenarios() -> list[dict[str, Any]]:
    root = files(_SCENARIO_PACKAGE)
    manifests = [
        _load_manifest(item)
        for item in root.iterdir()
        if item.name.endswith(".json")
    ]
    return sorted(manifests, key=lambda item: (int(item.get("order", 999)), item["name"]))


def scenario_names() -> list[str]:
    return [manifest["name"] for manifest in load_scenarios()]


def _step_size(step: dict[str, Any], profile: str) -> int:
    key = f"{profile}_bytes"
    value = step.get(key, step.get("bytes", 0))
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Step byte size {key!r} must be a non-negative integer.")
    return value


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _record(timestamp: str, payload: dict[str, Any]) -> str:
    return json.dumps({"timestamp": timestamp, "payload": payload}, separators=(",", ":"))


def _apply_step(
    lines: list[str],
    step: dict[str, Any],
    profile: str,
    timestamp: str,
) -> tuple[list[str], str]:
    kind = str(step.get("kind", "")).strip().lower()
    size = _step_size(step, profile)

    if kind == "text":
        lines.append(_record(timestamp, {"type": "user_message", "text": "x" * size}))
    elif kind == "image":
        lines.append(
            _record(
                timestamp,
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64," + ("A" * size),
                },
            )
        )
    elif kind == "tool_output":
        lines.append(_record(timestamp, {"type": "tool_result", "output": "T" * size}))
    elif kind == "token_usage":
        input_tokens = int(step.get("input_tokens", 100_000))
        cached_input_tokens = int(step.get("cached_input_tokens", 95_000))
        total_tokens = int(step.get("total_tokens", input_tokens + 500))
        lines.append(
            _record(
                timestamp,
                {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached_input_tokens,
                            "total_tokens": total_tokens,
                        }
                    },
                },
            )
        )
    elif kind == "malformed":
        lines.append(str(step.get("content", "{broken")))
    elif kind == "compact":
        summary = _record(
            timestamp,
            {
                "type": "compaction_summary",
                "summary": "S" * size,
            },
        )
        marker = _record(timestamp, {"type": "compaction"})
        lines = [marker, summary]
    else:
        raise ValueError(f"Unknown benchmark step kind: {kind!r}")

    return lines, kind


def _write_projection(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _expectation_list(expect: dict[str, Any], key: str) -> list[str]:
    value = expect.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Expectation {key!r} must be a list of strings.")
    return [item.upper() for item in value]


def _threshold_bytes(expect: dict[str, Any]) -> int | None:
    value = expect.get("before_payload_bytes")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("before_payload_bytes must be a positive integer.")
    return value


def run_scenario(
    manifest: dict[str, Any],
    profile: str = "ci",
) -> BenchmarkResult:
    if profile not in _ALLOWED_PROFILES:
        choices = ", ".join(sorted(_ALLOWED_PROFILES))
        raise ValueError(f"Unknown benchmark profile {profile!r}. Available: {choices}.")

    expect = manifest["expect"]
    must_detect = _expectation_list(expect, "must_detect")
    must_not_detect = _expectation_list(expect, "must_not_detect")
    threshold = _threshold_bytes(expect)
    interval_seconds = int(manifest.get("interval_seconds", 60))
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive.")

    observed: set[str] = set()
    unexpected: set[str] = set()
    step_results: list[BenchmarkStepResult] = []
    first_detection_step: int | None = None
    first_detection_payload: int | None = None
    peak_payload = 0
    total_analysis_ms = 0.0

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    previous_artifact: dict[str, Any] | None = None
    lines: list[str] = []

    with tempfile.TemporaryDirectory(prefix="cpg-benchmark-") as temp_dir:
        projection = Path(temp_dir) / f"{manifest['name']}.jsonl"

        for index, step in enumerate(manifest["steps"], start=1):
            captured = base_time + timedelta(seconds=index * interval_seconds)
            captured_at = _iso(captured)
            lines, kind = _apply_step(lines, step, profile, captured_at)
            _write_projection(projection, lines)

            started = perf_counter()
            snapshot = analyze_rollout(projection)
            snapshot.findings = run_detectors(snapshot)
            analysis_ms = (perf_counter() - started) * 1000
            total_analysis_ms += analysis_ms

            current_artifact = make_snapshot_artifact(snapshot, captured_at=captured_at)
            step_codes = {finding.code for finding in snapshot.findings}
            if previous_artifact is not None:
                growth = compare_artifacts(previous_artifact, current_artifact)
                step_codes.update(finding.code for finding in growth.findings)

            observed.update(step_codes)
            unexpected.update(step_codes.intersection(must_not_detect))
            peak_payload = max(peak_payload, snapshot.estimated_payload_bytes)

            if first_detection_step is None and any(code in step_codes for code in must_detect):
                first_detection_step = index
                first_detection_payload = snapshot.estimated_payload_bytes

            step_results.append(
                BenchmarkStepResult(
                    step=index,
                    kind=kind,
                    payload_bytes=snapshot.estimated_payload_bytes,
                    risk=snapshot.risk_label,
                    findings=sorted(step_codes),
                    analysis_ms=analysis_ms,
                )
            )
            previous_artifact = current_artifact

    missing = set(must_detect).difference(observed)
    early_enough = True
    lead_bytes: int | None = None
    if threshold is not None and must_detect:
        if first_detection_payload is None:
            early_enough = False
        else:
            lead_bytes = threshold - first_detection_payload
            early_enough = first_detection_payload < threshold

    passed = not missing and not unexpected and early_enough

    return BenchmarkResult(
        name=manifest["name"],
        description=str(manifest.get("description", "")),
        passed=passed,
        expected_findings=must_detect,
        forbidden_findings=must_not_detect,
        observed_findings=sorted(observed),
        unexpected_findings=sorted(unexpected),
        first_detection_step=first_detection_step,
        first_detection_payload_bytes=first_detection_payload,
        threshold_bytes=threshold,
        lead_bytes=lead_bytes,
        peak_payload_bytes=peak_payload,
        duration_ms=total_analysis_ms,
        steps=step_results,
    )


def run_benchmark_suite(
    profile: str = "ci",
    scenario: str | None = None,
) -> BenchmarkSuiteResult:
    if profile not in _ALLOWED_PROFILES:
        choices = ", ".join(sorted(_ALLOWED_PROFILES))
        raise ValueError(f"Unknown benchmark profile {profile!r}. Available: {choices}.")

    manifests = load_scenarios()
    if scenario is not None:
        normalized = scenario.strip().lower()
        manifests = [item for item in manifests if item["name"].lower() == normalized]
        if not manifests:
            choices = ", ".join(item["name"] for item in load_scenarios())
            raise ValueError(f"Unknown scenario {scenario!r}. Available: {choices}.")

    started = perf_counter()
    results = [run_scenario(manifest, profile=profile) for manifest in manifests]
    elapsed_ms = (perf_counter() - started) * 1000
    return BenchmarkSuiteResult(
        profile=profile,
        passed=all(result.passed for result in results),
        results=results,
        duration_ms=elapsed_ms,
    )

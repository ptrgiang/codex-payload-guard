from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Finding, GrowthComparison, Snapshot

SNAPSHOT_SCHEMA_VERSION = 1
_MIB = 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_snapshot_artifact(snapshot: Snapshot, captured_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "captured_at": captured_at or _now_iso(),
        "snapshot": snapshot.to_dict(),
    }


def write_snapshot_artifact(
    snapshot: Snapshot,
    output: Path,
    captured_at: str | None = None,
) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = make_snapshot_artifact(snapshot, captured_at=captured_at)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def load_snapshot_artifact(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Snapshot file must contain a JSON object.")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported snapshot schema: {payload.get('schema_version')!r}; "
            f"expected {SNAPSHOT_SCHEMA_VERSION}."
        )
    captured_at = payload.get("captured_at")
    snapshot = payload.get("snapshot")
    if not isinstance(captured_at, str) or not isinstance(snapshot, dict):
        raise ValueError("Snapshot file is missing captured_at or snapshot data.")
    return payload


def _parse_time(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_metric(snapshot: dict[str, Any], key: str) -> int:
    value = snapshot.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Snapshot metric {key!r} must be an integer.")
    return value


def _optional_int_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    key: str,
) -> int | None:
    before_value = before.get(key)
    after_value = after.get(key)
    if isinstance(before_value, int) and isinstance(after_value, int):
        return after_value - before_value
    return None


def _comparison_findings(
    payload_delta: int,
    media_delta: int,
    compactions_delta: int,
    elapsed_seconds: float,
) -> list[Finding]:
    findings: list[Finding] = []

    if payload_delta >= 8 * _MIB and compactions_delta <= 0:
        findings.append(
            Finding(
                code="PAYLOAD_GROWTH_SPIKE",
                severity="high",
                title="Payload grew rapidly between snapshots",
                message="Observed serialized payload increased by at least 8 MiB without a new compaction.",
                evidence={
                    "payload_delta_bytes": payload_delta,
                    "compactions_delta": compactions_delta,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                },
                action="Inspect the largest growth source before continuing the same session.",
            )
        )
    elif payload_delta >= 4 * _MIB and compactions_delta <= 0:
        findings.append(
            Finding(
                code="PAYLOAD_GROWTH_RISING",
                severity="medium",
                title="Payload is rising between snapshots",
                message="Observed serialized payload increased by at least 4 MiB without a new compaction.",
                evidence={
                    "payload_delta_bytes": payload_delta,
                    "compactions_delta": compactions_delta,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                },
                action="Continue monitoring growth before adding large media or verbose tool output.",
            )
        )

    if payload_delta > 0 and media_delta >= 4 * _MIB and media_delta / payload_delta >= 0.6:
        findings.append(
            Finding(
                code="MEDIA_GROWTH_DOMINANT",
                severity="high",
                title="Media accounts for most recent growth",
                message="Embedded media contributed at least 60% of positive payload growth.",
                evidence={
                    "payload_delta_bytes": payload_delta,
                    "media_delta_bytes": media_delta,
                    "media_growth_share": round(media_delta / payload_delta, 4),
                },
                action="Avoid adding more inline media until the active context is reduced.",
            )
        )

    if compactions_delta > 0 and payload_delta < 0:
        findings.append(
            Finding(
                code="COMPACTION_REDUCED_PAYLOAD",
                severity="low",
                title="Compaction coincided with payload reduction",
                message="A new compaction was observed and the estimated payload decreased.",
                evidence={
                    "payload_delta_bytes": payload_delta,
                    "compactions_delta": compactions_delta,
                },
                signal="observed",
            )
        )

    return findings


def compare_artifacts(before: dict[str, Any], after: dict[str, Any]) -> GrowthComparison:
    before_snapshot = before["snapshot"]
    after_snapshot = after["snapshot"]
    if not isinstance(before_snapshot, dict) or not isinstance(after_snapshot, dict):
        raise ValueError("Both artifacts must contain snapshot objects.")

    before_time = _parse_time(before["captured_at"])
    after_time = _parse_time(after["captured_at"])
    elapsed_seconds = max((after_time - before_time).total_seconds(), 0.0)

    payload_delta = _int_metric(after_snapshot, "estimated_payload_bytes") - _int_metric(
        before_snapshot, "estimated_payload_bytes"
    )
    records_delta = _int_metric(after_snapshot, "records") - _int_metric(before_snapshot, "records")
    media_delta = _int_metric(after_snapshot, "media_bytes") - _int_metric(
        before_snapshot, "media_bytes"
    )
    compactions_delta = _int_metric(after_snapshot, "compactions") - _int_metric(
        before_snapshot, "compactions"
    )

    bytes_per_minute = None
    if elapsed_seconds > 0:
        bytes_per_minute = payload_delta / (elapsed_seconds / 60)

    bytes_per_record = None
    if records_delta > 0:
        bytes_per_record = payload_delta / records_delta

    if payload_delta <= -1 * _MIB:
        trajectory = "IMPROVING"
    elif payload_delta >= 1 * _MIB:
        trajectory = "RISING"
    else:
        trajectory = "STABLE"

    return GrowthComparison(
        before_captured_at=before["captured_at"],
        after_captured_at=after["captured_at"],
        before_risk=str(before_snapshot.get("risk", "UNKNOWN")),
        after_risk=str(after_snapshot.get("risk", "UNKNOWN")),
        elapsed_seconds=elapsed_seconds,
        payload_delta_bytes=payload_delta,
        text_delta_bytes=_int_metric(after_snapshot, "text_bytes")
        - _int_metric(before_snapshot, "text_bytes"),
        media_delta_bytes=media_delta,
        tool_output_delta_bytes=_int_metric(after_snapshot, "tool_output_bytes")
        - _int_metric(before_snapshot, "tool_output_bytes"),
        other_delta_bytes=_int_metric(after_snapshot, "other_bytes")
        - _int_metric(before_snapshot, "other_bytes"),
        records_delta=records_delta,
        media_items_delta=_int_metric(after_snapshot, "media_items")
        - _int_metric(before_snapshot, "media_items"),
        compactions_delta=compactions_delta,
        input_tokens_delta=_optional_int_delta(before_snapshot, after_snapshot, "token_input"),
        bytes_per_minute=bytes_per_minute,
        bytes_per_record=bytes_per_record,
        trajectory=trajectory,
        findings=_comparison_findings(
            payload_delta=payload_delta,
            media_delta=media_delta,
            compactions_delta=compactions_delta,
            elapsed_seconds=elapsed_seconds,
        ),
    )


def compare_snapshot_files(before_path: Path, after_path: Path) -> GrowthComparison:
    before = load_snapshot_artifact(before_path)
    after = load_snapshot_artifact(after_path)
    return compare_artifacts(before, after)

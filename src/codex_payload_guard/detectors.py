from __future__ import annotations

from .models import Finding, Snapshot

_MIB = 1024 * 1024


def run_detectors(snapshot: Snapshot) -> list[Finding]:
    findings: list[Finding] = []
    total = snapshot.estimated_payload_bytes

    if total >= 48 * _MIB:
        findings.append(
            Finding(
                code="PAYLOAD_SIZE_CRITICAL",
                severity="critical",
                title="Estimated payload is critically large",
                message="Observed rollout content is already in a range associated with severe request-size risk.",
                evidence={"estimated_bytes": total, "threshold_bytes": 48 * _MIB},
                signal="inferred",
                action="Consider compacting or starting a clean continuation before adding more context.",
            )
        )
    elif total >= 24 * _MIB:
        findings.append(
            Finding(
                code="PAYLOAD_SIZE_HIGH",
                severity="high",
                title="Estimated payload is large",
                message="The observed session payload has crossed the high-risk byte threshold.",
                evidence={"estimated_bytes": total, "threshold_bytes": 24 * _MIB},
                signal="inferred",
                action="Inspect the payload breakdown and avoid unnecessary large inline artifacts.",
            )
        )

    if snapshot.media_share >= 0.60 and snapshot.media_bytes >= 8 * _MIB:
        findings.append(
            Finding(
                code="MEDIA_DOMINATED_CONTEXT",
                severity="high",
                title="Embedded media dominates the payload",
                message="Most observed payload bytes come from embedded media/data URLs.",
                evidence={
                    "media_bytes": snapshot.media_bytes,
                    "media_share": round(snapshot.media_share, 4),
                    "media_items": snapshot.media_items,
                },
                action="Prefer fewer inline images and compact before continuing image-heavy work.",
            )
        )

    if snapshot.tool_output_bytes >= 8 * _MIB:
        findings.append(
            Finding(
                code="OVERSIZED_TOOL_OUTPUT",
                severity="high",
                title="Tool outputs are consuming substantial context",
                message="Observed tool-returned text is large enough to materially inflate serialized history.",
                evidence={
                    "tool_output_bytes": snapshot.tool_output_bytes,
                    "tool_outputs": snapshot.tool_outputs,
                },
                action="Reduce verbose tool output or summarize large command results before continuing.",
            )
        )

    if total >= 16 * _MIB and snapshot.compactions == 0:
        findings.append(
            Finding(
                code="NO_COMPACTION_LONG_SESSION",
                severity="medium",
                title="Large session without observed compaction",
                message="No compaction event was detected while observed payload size is already substantial.",
                evidence={"estimated_bytes": total, "compactions": 0},
                action="Consider /compact if the active task can safely continue from a compressed history.",
            )
        )

    if snapshot.malformed_records:
        findings.append(
            Finding(
                code="MALFORMED_ROLLOUT_RECORDS",
                severity="medium",
                title="Some rollout records could not be parsed",
                message="Payload estimates are incomplete because malformed JSONL records were skipped.",
                evidence={"malformed_records": snapshot.malformed_records},
                signal="observed",
            )
        )

    if snapshot.token_input and snapshot.cached_input is not None and total >= 16 * _MIB:
        cache_ratio = snapshot.cached_input / snapshot.token_input if snapshot.token_input else 0
        if cache_ratio >= 0.9:
            findings.append(
                Finding(
                    code="HIGH_BYTES_HIGH_CACHE",
                    severity="medium",
                    title="High token-cache reuse may hide byte pressure",
                    message="Cached token usage is high while observed serialized payload is also large.",
                    evidence={
                        "estimated_bytes": total,
                        "input_tokens": snapshot.token_input,
                        "cached_input_tokens": snapshot.cached_input,
                        "cache_ratio": round(cache_ratio, 4),
                    },
                    signal="inferred",
                    action="Use byte-level payload size alongside token metrics when judging session health.",
                )
            )

    return findings


FINDING_HELP = {
    "MEDIA_DOMINATED_CONTEXT": "Embedded image/data-URL bytes account for most observed payload bytes.",
    "OVERSIZED_TOOL_OUTPUT": "Large stdout/stderr/tool results are accumulating in serialized history.",
    "NO_COMPACTION_LONG_SESSION": "The session is already large and no compaction event was observed.",
    "PAYLOAD_SIZE_HIGH": "Observed content crossed the default 24 MiB high-risk threshold.",
    "PAYLOAD_SIZE_CRITICAL": "Observed content crossed the default 48 MiB critical threshold.",
    "HIGH_BYTES_HIGH_CACHE": "High cached-token reuse does not imply a small serialized request body.",
    "MALFORMED_ROLLOUT_RECORDS": "One or more JSONL records were unreadable, so estimates are incomplete.",
    "PAYLOAD_GROWTH_RISING": "Payload increased by at least 4 MiB between snapshots without a new compaction.",
    "PAYLOAD_GROWTH_SPIKE": "Payload increased by at least 8 MiB between snapshots without a new compaction.",
    "MEDIA_GROWTH_DOMINANT": "Embedded media contributed at least 60% of positive growth between snapshots.",
    "COMPACTION_REDUCED_PAYLOAD": "A newly observed compaction coincided with lower estimated payload bytes.",
}

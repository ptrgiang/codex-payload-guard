from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["low", "medium", "high", "critical"]
SignalKind = Literal["observed", "inferred", "unknown"]

_SEVERITY_ORDER: dict[Severity, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(slots=True)
class Finding:
    code: str
    severity: Severity
    title: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    signal: SignalKind = "observed"
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Snapshot:
    path: Path
    records: int = 0
    malformed_records: int = 0
    file_bytes: int = 0
    observed_json_bytes: int = 0
    text_bytes: int = 0
    media_bytes: int = 0
    tool_output_bytes: int = 0
    other_bytes: int = 0
    media_items: int = 0
    tool_outputs: int = 0
    compactions: int = 0
    token_total: int | None = None
    token_input: int | None = None
    cached_input: int | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def estimated_payload_bytes(self) -> int:
        return self.text_bytes + self.media_bytes + self.tool_output_bytes + self.other_bytes

    @property
    def media_share(self) -> float:
        total = self.estimated_payload_bytes
        return 0.0 if total == 0 else self.media_bytes / total

    @property
    def risk_label(self) -> str:
        if not self.findings:
            return "LOW"
        severity = max(self.findings, key=lambda item: _SEVERITY_ORDER[item.severity]).severity
        return severity.upper()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["estimated_payload_bytes"] = self.estimated_payload_bytes
        data["media_share"] = self.media_share
        data["risk"] = self.risk_label
        data["findings"] = [item.to_dict() for item in self.findings]
        return data


@dataclass(slots=True)
class GrowthComparison:
    before_captured_at: str
    after_captured_at: str
    before_risk: str
    after_risk: str
    elapsed_seconds: float
    payload_delta_bytes: int
    text_delta_bytes: int
    media_delta_bytes: int
    tool_output_delta_bytes: int
    other_delta_bytes: int
    records_delta: int
    media_items_delta: int
    compactions_delta: int
    input_tokens_delta: int | None
    bytes_per_minute: float | None
    bytes_per_record: float | None
    trajectory: str
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [item.to_dict() for item in self.findings]
        return data

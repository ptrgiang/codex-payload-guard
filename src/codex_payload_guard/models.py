from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["low", "medium", "high", "critical"]
SignalKind = Literal["observed", "inferred", "unknown"]


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

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["estimated_payload_bytes"] = self.estimated_payload_bytes
        data["media_share"] = self.media_share
        data["findings"] = [item.to_dict() for item in self.findings]
        return data

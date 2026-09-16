from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class BenchmarkStepResult:
    step: int
    kind: str
    payload_bytes: int
    risk: str
    findings: list[str] = field(default_factory=list)
    analysis_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BenchmarkResult:
    name: str
    description: str
    passed: bool
    expected_findings: list[str]
    forbidden_findings: list[str]
    observed_findings: list[str]
    unexpected_findings: list[str]
    first_detection_step: int | None
    first_detection_payload_bytes: int | None
    threshold_bytes: int | None
    lead_bytes: int | None
    peak_payload_bytes: int
    duration_ms: float
    steps: list[BenchmarkStepResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.to_dict() for step in self.steps]
        return data


@dataclass(slots=True)
class BenchmarkSuiteResult:
    profile: str
    passed: bool
    results: list[BenchmarkResult]
    duration_ms: float

    @property
    def passed_count(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def failed_count(self) -> int:
        return len(self.results) - self.passed_count

    @property
    def false_positive_count(self) -> int:
        return sum(bool(result.unexpected_findings) for result in self.results)

    @property
    def median_lead_bytes(self) -> float | None:
        leads = sorted(
            result.lead_bytes
            for result in self.results
            if result.lead_bytes is not None and result.lead_bytes >= 0
        )
        if not leads:
            return None
        middle = len(leads) // 2
        if len(leads) % 2:
            return float(leads[middle])
        return (leads[middle - 1] + leads[middle]) / 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "passed": self.passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "false_positive_count": self.false_positive_count,
            "median_lead_bytes": self.median_lead_bytes,
            "duration_ms": self.duration_ms,
            "results": [result.to_dict() for result in self.results],
        }

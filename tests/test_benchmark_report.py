import json

from codex_payload_guard.benchmark import run_benchmark_suite
from codex_payload_guard.benchmark_report import (
    BENCHMARK_REPORT_SCHEMA_VERSION,
    make_benchmark_evidence,
    render_benchmark_markdown,
    scenario_fingerprint,
    write_benchmark_evidence,
)


def test_scenario_fingerprint_is_stable_sha256() -> None:
    first = scenario_fingerprint()
    second = scenario_fingerprint()
    assert first == second
    assert len(first) == 64
    int(first, 16)


def test_evidence_envelope_contains_audit_metadata() -> None:
    suite = run_benchmark_suite(profile="ci", scenario="payload-spike")
    evidence = make_benchmark_evidence(
        suite,
        generated_at="2026-09-16T00:00:00Z",
    )

    assert evidence["schema_version"] == BENCHMARK_REPORT_SCHEMA_VERSION
    assert evidence["generated_at"] == "2026-09-16T00:00:00Z"
    assert evidence["measurement_model"] == "deterministic-active-payload-projection"
    assert len(evidence["scenario_fingerprint_sha256"]) == 64
    assert evidence["tool"]["name"] == "codex-payload-guard"
    assert evidence["environment"]["python_version"]
    assert evidence["suite"]["passed"] is True


def test_markdown_report_contains_summary_and_scenario() -> None:
    suite = run_benchmark_suite(profile="ci", scenario="payload-spike")
    evidence = make_benchmark_evidence(
        suite,
        generated_at="2026-09-16T00:00:00Z",
    )
    markdown = render_benchmark_markdown(evidence)

    assert "# Codex Payload Guard Benchmark Evidence" in markdown
    assert "Detection coverage" in markdown
    assert "payload-spike" in markdown
    assert "Scenario fingerprint" in markdown


def test_write_benchmark_evidence_creates_json_and_markdown(tmp_path) -> None:
    suite = run_benchmark_suite(profile="ci", scenario="payload-spike")
    json_path, markdown_path = write_benchmark_evidence(suite, tmp_path / "evidence")

    assert json_path.is_file()
    assert markdown_path.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["suite"]["passed"] is True
    assert payload["scenario_fingerprint_sha256"] == scenario_fingerprint()
    assert "payload-spike" in markdown_path.read_text(encoding="utf-8")

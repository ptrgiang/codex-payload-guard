from codex_payload_guard.benchmark import load_scenarios, run_benchmark_suite, run_scenario


def _scenario(name: str) -> dict:
    for manifest in load_scenarios():
        if manifest["name"] == name:
            return manifest
    raise AssertionError(f"Missing scenario: {name}")


def test_scenario_catalog_is_stable() -> None:
    names = [manifest["name"] for manifest in load_scenarios()]
    assert names == [
        "normal-text",
        "image-burst",
        "tool-output-flood",
        "steady-payload-growth",
        "payload-spike",
        "compaction-recovery",
        "high-cache-large-payload",
        "malformed-rollout",
    ]


def test_normal_text_has_no_false_positive() -> None:
    result = run_scenario(_scenario("normal-text"), profile="ci")
    assert result.passed
    assert result.observed_findings == []
    assert result.unexpected_findings == []


def test_image_burst_is_detected_before_high_threshold() -> None:
    result = run_scenario(_scenario("image-burst"), profile="ci")
    assert result.passed
    assert "MEDIA_GROWTH_DOMINANT" in result.observed_findings
    assert "MEDIA_DOMINATED_CONTEXT" in result.observed_findings
    assert result.lead_bytes is not None
    assert result.lead_bytes > 0


def test_compaction_recovery_is_observed() -> None:
    result = run_scenario(_scenario("compaction-recovery"), profile="ci")
    assert result.passed
    assert "COMPACTION_REDUCED_PAYLOAD" in result.observed_findings


def test_selected_scenario_suite() -> None:
    suite = run_benchmark_suite(profile="ci", scenario="payload-spike")
    assert suite.passed
    assert suite.passed_count == 1
    assert suite.failed_count == 0

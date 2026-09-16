import json
from pathlib import Path

from codex_payload_guard.analyzer import analyze_rollout
from codex_payload_guard.detectors import run_detectors


def _write(path: Path, records: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def test_normal_rollout_is_low_risk(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "rollout-normal.jsonl",
        [
            {"timestamp": "2026-09-16T00:00:00Z", "payload": {"type": "user_message", "text": "hello"}},
            {"timestamp": "2026-09-16T00:00:01Z", "payload": {"type": "assistant_message", "text": "hi"}},
        ],
    )
    snapshot = analyze_rollout(path)
    findings = run_detectors(snapshot)
    assert snapshot.records == 2
    assert snapshot.text_bytes >= 7
    assert findings == []


def test_media_dominated_context_is_detected(tmp_path: Path) -> None:
    image = "data:image/png;base64," + ("A" * (9 * 1024 * 1024))
    path = _write(
        tmp_path / "rollout-image.jsonl",
        [{"timestamp": "2026-09-16T00:00:00Z", "payload": {"image_url": image}}],
    )
    snapshot = analyze_rollout(path)
    findings = run_detectors(snapshot)
    codes = {finding.code for finding in findings}
    assert snapshot.media_items == 1
    assert "MEDIA_DOMINATED_CONTEXT" in codes


def test_malformed_record_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "rollout-bad.jsonl"
    path.write_text('{"timestamp":"ok","payload":{"text":"hello"}}\n{broken\n', encoding="utf-8")
    snapshot = analyze_rollout(path)
    findings = run_detectors(snapshot)
    assert snapshot.malformed_records == 1
    assert "MALFORMED_ROLLOUT_RECORDS" in {finding.code for finding in findings}


def test_token_cache_signal(tmp_path: Path) -> None:
    large_text = "x" * (17 * 1024 * 1024)
    path = _write(
        tmp_path / "rollout-cache.jsonl",
        [
            {"payload": {"text": large_text}},
            {
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100_000,
                            "cached_input_tokens": 95_000,
                            "total_tokens": 100_500,
                        }
                    },
                }
            },
        ],
    )
    snapshot = analyze_rollout(path)
    codes = {finding.code for finding in run_detectors(snapshot)}
    assert "HIGH_BYTES_HIGH_CACHE" in codes

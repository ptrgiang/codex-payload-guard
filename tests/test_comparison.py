from pathlib import Path

import pytest

from codex_payload_guard.comparison import (
    compare_artifacts,
    load_snapshot_artifact,
    make_snapshot_artifact,
    write_snapshot_artifact,
)
from codex_payload_guard.detectors import run_detectors
from codex_payload_guard.models import Snapshot

_MIB = 1024 * 1024


def _measured(
    tmp_path: Path,
    name: str,
    *,
    text_bytes: int = 0,
    media_bytes: int = 0,
    tool_output_bytes: int = 0,
    records: int = 0,
    media_items: int = 0,
    compactions: int = 0,
) -> Snapshot:
    measured = Snapshot(
        path=tmp_path / name,
        text_bytes=text_bytes,
        media_bytes=media_bytes,
        tool_output_bytes=tool_output_bytes,
        records=records,
        media_items=media_items,
        compactions=compactions,
    )
    measured.findings = run_detectors(measured)
    return measured


def test_snapshot_artifact_round_trip(tmp_path: Path) -> None:
    measured = _measured(tmp_path, "rollout.jsonl", text_bytes=2 * _MIB, records=10)
    output = tmp_path / "before.json"

    write_snapshot_artifact(measured, output, captured_at="2026-09-16T00:00:00Z")
    loaded = load_snapshot_artifact(output)

    assert loaded["schema_version"] == 1
    assert loaded["captured_at"] == "2026-09-16T00:00:00Z"
    assert loaded["snapshot"]["estimated_payload_bytes"] == 2 * _MIB
    assert loaded["snapshot"]["risk"] == "LOW"


def test_compare_detects_growth_spike_and_velocity(tmp_path: Path) -> None:
    before = _measured(tmp_path, "before.jsonl", text_bytes=2 * _MIB, records=10)
    after = _measured(tmp_path, "after.jsonl", text_bytes=12 * _MIB, records=20)

    result = compare_artifacts(
        make_snapshot_artifact(before, "2026-09-16T00:00:00Z"),
        make_snapshot_artifact(after, "2026-09-16T00:01:00Z"),
    )

    assert result.payload_delta_bytes == 10 * _MIB
    assert result.records_delta == 10
    assert result.bytes_per_minute == pytest.approx(10 * _MIB)
    assert result.bytes_per_record == pytest.approx(1 * _MIB)
    assert result.trajectory == "RISING"
    assert "PAYLOAD_GROWTH_SPIKE" in {finding.code for finding in result.findings}


def test_compare_detects_media_dominated_growth(tmp_path: Path) -> None:
    before = _measured(tmp_path, "before.jsonl", text_bytes=2 * _MIB, records=10)
    after = _measured(
        tmp_path,
        "after.jsonl",
        text_bytes=3 * _MIB,
        media_bytes=8 * _MIB,
        records=14,
        media_items=2,
    )

    result = compare_artifacts(
        make_snapshot_artifact(before, "2026-09-16T00:00:00Z"),
        make_snapshot_artifact(after, "2026-09-16T00:02:00Z"),
    )

    codes = {finding.code for finding in result.findings}
    assert result.media_delta_bytes == 8 * _MIB
    assert "MEDIA_GROWTH_DOMINANT" in codes


def test_compaction_reduction_is_reported(tmp_path: Path) -> None:
    before = _measured(tmp_path, "before.jsonl", text_bytes=20 * _MIB, records=100)
    after = _measured(
        tmp_path,
        "after.jsonl",
        text_bytes=6 * _MIB,
        records=110,
        compactions=1,
    )

    result = compare_artifacts(
        make_snapshot_artifact(before, "2026-09-16T00:00:00Z"),
        make_snapshot_artifact(after, "2026-09-16T00:05:00Z"),
    )

    assert result.payload_delta_bytes == -14 * _MIB
    assert result.trajectory == "IMPROVING"
    assert "COMPACTION_REDUCED_PAYLOAD" in {finding.code for finding in result.findings}


def test_unknown_snapshot_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.json"
    path.write_text(
        '{"schema_version":99,"captured_at":"2026-09-16T00:00:00Z","snapshot":{}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported snapshot schema"):
        load_snapshot_artifact(path)

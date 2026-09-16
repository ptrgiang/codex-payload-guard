from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .models import Snapshot

_TEXT_KEYS = {"text", "input_text", "output_text", "message", "summary", "reasoning"}
_TOOL_KEYS = {"output", "stdout", "stderr", "result"}
_IMAGE_KEYS = {"image_url", "input_image", "image"}


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8", errors="replace"))


def _is_data_url(value: str) -> bool:
    return value.startswith("data:image/") or value.startswith("data:application/octet-stream")


def _walk(value: Any, parent_key: str | None = None) -> Iterator[tuple[str | None, Any]]:
    yield parent_key, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, parent_key)


def _extract_usage(record: dict[str, Any], snapshot: Snapshot) -> None:
    for _, node in _walk(record):
        if not isinstance(node, dict):
            continue
        usage = node.get("last_token_usage")
        if not isinstance(usage, dict):
            continue
        total = usage.get("total_tokens")
        input_tokens = usage.get("input_tokens")
        cached = usage.get("cached_input_tokens")
        if isinstance(total, int):
            snapshot.token_total = total
        if isinstance(input_tokens, int):
            snapshot.token_input = input_tokens
        if isinstance(cached, int):
            snapshot.cached_input = cached


def _is_compaction(record: dict[str, Any]) -> bool:
    for key, node in _walk(record):
        if isinstance(node, str) and key in {"type", "name", "event"}:
            lowered = node.lower()
            if "compact" in lowered or "compaction" in lowered:
                return True
    return False


def _classify_record(record: dict[str, Any], snapshot: Snapshot) -> None:
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str):
        snapshot.first_timestamp = snapshot.first_timestamp or timestamp
        snapshot.last_timestamp = timestamp

    if _is_compaction(record):
        snapshot.compactions += 1

    _extract_usage(record, snapshot)

    seen_strings: set[int] = set()
    for key, node in _walk(record):
        if not isinstance(node, str):
            continue
        identity = id(node)
        if identity in seen_strings:
            continue
        seen_strings.add(identity)
        size = _utf8_len(node)
        lowered_key = (key or "").lower()

        if _is_data_url(node) or lowered_key in _IMAGE_KEYS and node.startswith("data:"):
            snapshot.media_bytes += size
            snapshot.media_items += 1
        elif lowered_key in _TOOL_KEYS:
            snapshot.tool_output_bytes += size
            snapshot.tool_outputs += 1
        elif lowered_key in _TEXT_KEYS or "text" in lowered_key or "message" in lowered_key:
            snapshot.text_bytes += size
        elif size >= 4096:
            snapshot.other_bytes += size


def analyze_rollout(path: Path) -> Snapshot:
    path = path.expanduser().resolve()
    snapshot = Snapshot(path=path, file_bytes=path.stat().st_size)

    with path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            snapshot.records += 1
            snapshot.observed_json_bytes += len(raw_line)
            try:
                record = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                snapshot.malformed_records += 1
                continue
            if isinstance(record, dict):
                _classify_record(record, snapshot)

    accounted = snapshot.text_bytes + snapshot.media_bytes + snapshot.tool_output_bytes
    snapshot.other_bytes = max(snapshot.other_bytes, snapshot.observed_json_bytes - accounted)
    return snapshot

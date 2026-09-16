from __future__ import annotations

import os
from pathlib import Path


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def discover_rollouts(root: Path | None = None) -> list[Path]:
    base = (root or codex_home()).expanduser()
    if not base.exists():
        return []
    files = [path for path in base.rglob("rollout-*.jsonl") if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def latest_rollout(root: Path | None = None) -> Path | None:
    items = discover_rollouts(root)
    return items[0] if items else None

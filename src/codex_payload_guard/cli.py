from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .analyzer import analyze_rollout
from .benchmark_cli import register_benchmark
from .comparison import (
    compare_artifacts,
    compare_snapshot_files,
    make_snapshot_artifact,
    write_snapshot_artifact,
)
from .detectors import FINDING_HELP, run_detectors
from .discovery import discover_rollouts, latest_rollout
from .models import GrowthComparison

app = typer.Typer(help="Local-first byte-budget watchdog for OpenAI Codex sessions.")
console = Console()
_MIB = 1024 * 1024


def _fmt_bytes(value: int | float) -> str:
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    if absolute < 1024:
        return f"{sign}{absolute:.0f} B"
    if absolute < _MIB:
        return f"{sign}{absolute / 1024:.1f} KiB"
    return f"{sign}{absolute / _MIB:.1f} MiB"


def _fmt_signed_bytes(value: int | float) -> str:
    if value == 0:
        return "0 B"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{_fmt_bytes(value)}"


def _resolve(path: Path | None, latest: bool, root: Path | None) -> Path:
    if path is not None:
        return path
    if latest:
        found = latest_rollout(root)
        if found is None:
            raise typer.BadParameter("No Codex rollout files were found.")
        return found
    raise typer.BadParameter("Provide PATH or use --latest.")


def _render(snapshot) -> None:
    table = Table(title="Codex Payload Guard", show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Session", snapshot.path.name)
    table.add_row("Rollout file", _fmt_bytes(snapshot.file_bytes))
    table.add_row("Estimated payload", _fmt_bytes(snapshot.estimated_payload_bytes))
    table.add_row("Text", _fmt_bytes(snapshot.text_bytes))
    table.add_row("Embedded media", _fmt_bytes(snapshot.media_bytes))
    table.add_row("Tool output", _fmt_bytes(snapshot.tool_output_bytes))
    table.add_row("Other JSON", _fmt_bytes(snapshot.other_bytes))
    table.add_row("Media items", str(snapshot.media_items))
    table.add_row("Compactions", str(snapshot.compactions))
    if snapshot.token_input is not None:
        table.add_row("Input tokens", f"{snapshot.token_input:,}")
    if snapshot.cached_input is not None:
        table.add_row("Cached input", f"{snapshot.cached_input:,}")
    table.add_row("Risk", snapshot.risk_label)
    console.print(table)

    if snapshot.findings:
        console.print("\n[bold]Findings[/bold]")
        for finding in snapshot.findings:
            console.print(
                f"[{finding.severity.upper()}] [bold]{finding.code}[/bold] — {finding.message}"
            )
            if finding.action:
                console.print(f"  Action: {finding.action}")


def _render_growth(comparison: GrowthComparison, title: str = "Payload growth") -> None:
    table = Table(title=title, show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Risk", f"{comparison.before_risk} → {comparison.after_risk}")
    table.add_row("Trajectory", comparison.trajectory)
    table.add_row("Payload", _fmt_signed_bytes(comparison.payload_delta_bytes))
    table.add_row("Text", _fmt_signed_bytes(comparison.text_delta_bytes))
    table.add_row("Embedded media", _fmt_signed_bytes(comparison.media_delta_bytes))
    table.add_row("Tool output", _fmt_signed_bytes(comparison.tool_output_delta_bytes))
    table.add_row("Other JSON", _fmt_signed_bytes(comparison.other_delta_bytes))
    table.add_row("New records", f"{comparison.records_delta:+d}")
    table.add_row("Compactions", f"{comparison.compactions_delta:+d}")
    if comparison.input_tokens_delta is not None:
        table.add_row("Input tokens", f"{comparison.input_tokens_delta:+,}")
    if comparison.bytes_per_minute is not None:
        table.add_row("Velocity", f"{_fmt_signed_bytes(comparison.bytes_per_minute)}/min")
    if comparison.bytes_per_record is not None:
        table.add_row("Per new record", _fmt_signed_bytes(comparison.bytes_per_record))
    console.print(table)

    if comparison.findings:
        console.print("\n[bold]Growth findings[/bold]")
        for finding in comparison.findings:
            console.print(
                f"[{finding.severity.upper()}] [bold]{finding.code}[/bold] — {finding.message}"
            )
            if finding.action:
                console.print(f"  Action: {finding.action}")


@app.command()
def scan(
    root: Annotated[Path | None, typer.Option(help="Codex home/search root.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=200)] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """List recent rollout sessions."""
    rollouts = discover_rollouts(root)[:limit]
    if json_output:
        payload = [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "modified": path.stat().st_mtime,
            }
            for path in rollouts
        ]
        console.print_json(json.dumps(payload))
        return

    table = Table(title="Recent Codex rollouts")
    table.add_column("#", justify="right")
    table.add_column("File")
    table.add_column("Size", justify="right")
    for index, path in enumerate(rollouts, start=1):
        table.add_row(str(index), str(path), _fmt_bytes(path.stat().st_size))
    console.print(table)


@app.command()
def inspect(
    path: Annotated[Path | None, typer.Argument()] = None,
    latest: Annotated[bool, typer.Option("--latest")] = False,
    root: Annotated[Path | None, typer.Option(help="Codex home/search root.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Inspect payload composition and risk signals."""
    target = _resolve(path, latest, root)
    snapshot = analyze_rollout(target)
    snapshot.findings = run_detectors(snapshot)
    if json_output:
        console.print_json(json.dumps(snapshot.to_dict()))
    else:
        _render(snapshot)


@app.command()
def snapshot(
    path: Annotated[Path | None, typer.Argument()] = None,
    latest: Annotated[bool, typer.Option("--latest")] = False,
    root: Annotated[Path | None, typer.Option(help="Codex home/search root.")] = None,
    output: Annotated[
        Path,
        typer.Option("-o", "--output", help="Snapshot JSON output path."),
    ] = Path("cpg-snapshot.json"),
) -> None:
    """Capture a portable measurement point for later comparison."""
    target = _resolve(path, latest, root)
    measured = analyze_rollout(target)
    measured.findings = run_detectors(measured)
    written = write_snapshot_artifact(measured, output)
    console.print(f"Snapshot written: [bold]{written}[/bold]")
    console.print(
        f"Payload {_fmt_bytes(measured.estimated_payload_bytes)} · Risk {measured.risk_label}"
    )


@app.command("compare")
def compare_command(
    before: Annotated[Path, typer.Argument(help="Earlier snapshot JSON.")],
    after: Annotated[Path, typer.Argument(help="Later snapshot JSON.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Compare two snapshots and calculate byte-growth velocity."""
    try:
        comparison = compare_snapshot_files(before, after)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_output:
        console.print_json(json.dumps(comparison.to_dict()))
    else:
        _render_growth(comparison)


@app.command()
def watch(
    path: Annotated[Path | None, typer.Argument()] = None,
    latest: Annotated[bool, typer.Option("--latest")] = False,
    root: Annotated[Path | None, typer.Option(help="Codex home/search root.")] = None,
    interval: Annotated[float, typer.Option(min=1.0, help="Refresh interval in seconds.")] = 5.0,
) -> None:
    """Watch a rollout and refresh diagnostics when it changes."""
    target = _resolve(path, latest, root)
    previous_size = -1
    previous_artifact = None
    try:
        while True:
            size = target.stat().st_size
            if size != previous_size:
                measured = analyze_rollout(target)
                measured.findings = run_detectors(measured)
                current_artifact = make_snapshot_artifact(measured)

                console.clear()
                _render(measured)
                if previous_artifact is not None:
                    growth = compare_artifacts(previous_artifact, current_artifact)
                    console.print()
                    _render_growth(growth, title="Growth since previous change")

                console.print(f"\nWatching every {interval:g}s. Ctrl+C to stop.")
                previous_artifact = current_artifact
                previous_size = size
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\nStopped.")


@app.command()
def explain(code: Annotated[str, typer.Argument(help="Finding code")]) -> None:
    """Explain a detector finding code."""
    normalized = code.strip().upper()
    explanation = FINDING_HELP.get(normalized)
    if explanation is None:
        choices = ", ".join(sorted(FINDING_HELP))
        raise typer.BadParameter(f"Unknown code. Available: {choices}")
    console.print(f"[bold]{normalized}[/bold]\n{explanation}")


register_benchmark(app, console, _fmt_bytes)


if __name__ == "__main__":
    app()

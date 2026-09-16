from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .benchmark import run_benchmark_suite
from .benchmark_models import BenchmarkResult, BenchmarkSuiteResult


def _default_fmt_bytes(value: int | float) -> str:
    mib = 1024 * 1024
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    if absolute < 1024:
        return f"{sign}{absolute:.0f} B"
    if absolute < mib:
        return f"{sign}{absolute / 1024:.1f} KiB"
    return f"{sign}{absolute / mib:.1f} MiB"


def _render_result_steps(
    console: Console,
    result: BenchmarkResult,
    fmt_bytes: Callable[[int | float], str],
) -> None:
    table = Table(title=f"Trace · {result.name}")
    table.add_column("Step", justify="right")
    table.add_column("Kind")
    table.add_column("Payload", justify="right")
    table.add_column("Risk")
    table.add_column("Findings")
    table.add_column("Analyze", justify="right")
    for step in result.steps:
        findings = ", ".join(step.findings) if step.findings else "-"
        table.add_row(
            str(step.step),
            step.kind,
            fmt_bytes(step.payload_bytes),
            step.risk,
            findings,
            f"{step.analysis_ms:.1f} ms",
        )
    console.print(table)


def _render_suite(
    console: Console,
    suite: BenchmarkSuiteResult,
    verbose: bool,
    fmt_bytes: Callable[[int | float], str],
) -> None:
    table = Table(title=f"Codex Payload Guard Benchmark · {suite.profile}")
    table.add_column("Scenario")
    table.add_column("Expected")
    table.add_column("Lead", justify="right")
    table.add_column("Peak", justify="right")
    table.add_column("Result")

    for result in suite.results:
        expected = ", ".join(result.expected_findings) if result.expected_findings else "none"
        lead = fmt_bytes(result.lead_bytes) if result.lead_bytes is not None else "—"
        table.add_row(
            result.name,
            expected,
            lead,
            fmt_bytes(result.peak_payload_bytes),
            "PASS" if result.passed else "FAIL",
        )
    console.print(table)

    median = fmt_bytes(suite.median_lead_bytes) if suite.median_lead_bytes is not None else "—"
    console.print(
        f"\n{suite.passed_count}/{len(suite.results)} scenarios passed · "
        f"False-positive scenarios: {suite.false_positive_count} · "
        f"Median early-warning lead: {median} · "
        f"Runtime: {suite.duration_ms:.1f} ms"
    )

    if verbose:
        for result in suite.results:
            console.print()
            _render_result_steps(console, result, fmt_bytes)


def register_benchmark(
    app: typer.Typer,
    console: Console,
    fmt_bytes: Callable[[int | float], str] = _default_fmt_bytes,
) -> None:
    @app.command("benchmark")
    def benchmark_command(
        scenario: Annotated[
            str | None,
            typer.Argument(help="Optional scenario name."),
        ] = None,
        profile: Annotated[
            str,
            typer.Option("--profile", help="Benchmark profile: ci or full."),
        ] = "ci",
        json_output: Annotated[
            bool,
            typer.Option("--json", help="Emit machine-readable JSON."),
        ] = False,
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-v", help="Show the step-by-step trace."),
        ] = False,
    ) -> None:
        """Run deterministic payload-risk benchmark scenarios."""
        try:
            suite = run_benchmark_suite(profile=profile, scenario=scenario)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise typer.BadParameter(str(exc)) from exc

        if json_output:
            console.print_json(json.dumps(suite.to_dict()))
        else:
            _render_suite(console, suite, verbose=verbose, fmt_bytes=fmt_bytes)

        if not suite.passed:
            raise typer.Exit(code=1)

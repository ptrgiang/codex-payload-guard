from typer.testing import CliRunner

from codex_payload_guard import __version__
from codex_payload_guard.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"codex-payload-guard {__version__}"

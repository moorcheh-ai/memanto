"""CLI entrypoint behavior — argument parsing and config-error paths."""

from __future__ import annotations

import pytest

from memanto_mcp import __version__
from memanto_mcp.__main__ import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--version"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == __version__


def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "memanto-mcp" in out
    assert "--transport" in out


def test_missing_api_key_exits_with_code_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # _isolate_env in conftest has already stripped MOORCHEH_API_KEY.
    rc = main([])
    err = capsys.readouterr().err
    assert rc == 2
    assert "configuration error" in err.lower()
    # The error must be on stderr — stdout is reserved for JSON-RPC frames.
    assert "configuration error" not in capsys.readouterr().out


def test_invalid_transport_rejected_by_argparse(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--transport", "carrier-pigeon"])
    assert exc.value.code == 2

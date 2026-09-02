import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

CLI = Path(__file__).parent.parent / "cli.py"


class TestCLIPipeline:
    def test_invalid_source(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--source",
                "nonexistent",
                "--input",
                "/nonexistent/file.json",
                "--output",
                str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0

    def test_missing_input(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--source",
                "chatgpt",
                "--input",
                "/nonexistent/file.json",
                "--output",
                str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0

    def test_missing_source(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--input",
                "/nonexistent/file.json",
                "--output",
                str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
